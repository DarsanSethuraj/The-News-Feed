import os
import re
import html
import json
import logging
import threading
import unicodedata
from typing import List
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from google import genai
from google.genai import types
from database import SessionLocal
from models import Article
from Authentication.admin_auth import verify_admin

logger = logging.getLogger(__name__)
router = APIRouter()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

GEMINI_KEYS = [
    ("KEY_1", os.getenv("GEMINI_API_KEY_1")),
    ("KEY_2", os.getenv("GEMINI_API_KEY_2")),
    ("KEY_3", os.getenv("GEMINI_API_KEY_3")),
    ("KEY_4", os.getenv("GEMINI_API_KEY_4")),
    ("KEY_5", os.getenv("GEMINI_API_KEY_5")),
    ("KEY_6", os.getenv("GEMINI_API_KEY_6")),
]
GEMINI_KEYS = [(name, key) for name, key in GEMINI_KEYS if key]

_in_flight_lock = threading.Lock()
_in_flight_articles = set()

ALLOWED_TAGS = {"p", "br", "b", "i", "strong", "em", "ul", "ol", "li", "blockquote"}


# ==========================================
# 1. Pydantic Schemas
# ==========================================

class RewriteDraft(BaseModel):
    titles: List[str] = Field(
        min_length=4, 
        max_length=4, 
        description="4 distinct, engaging Malayalam headlines capturing different news angles."
    )
    content: str = Field(
        description="Complete, freshly rewritten Malayalam news article in HTML paragraphs (<p>)."
    )


class CritiqueReport(BaseModel):
    has_faults: bool = Field(
        description="True ONLY if real factual omissions, ungrounded external details, or corrupted numbers exist."
    )
    specific_faults: List[str] = Field(
        default_factory=list,
        description="Actionable points of what needs factual fixing."
    )


# ==========================================
# 2. Text and HTML Sanitization
# ==========================================

def clean_html_noise(raw_html: str) -> str:
    """Removes scripts, styles, and non-content noise while preserving article HTML tags (including <p>, <a>, etc.)."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav", "svg", "figure"]):
        tag.decompose()
    return str(soup).strip()


def sanitize_html(raw_html: str) -> str:
    """Sanitizes HTML content, stripping out disallowed tags and all attributes."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return "".join(str(c) for c in soup.contents).strip()


def verify_and_clean_output(data: RewriteDraft) -> dict:
    """Sanitizes headlines, normalizes Unicode, and cleans HTML body."""
    cleaned_titles = []
    seen = set()

    for t in data.titles:
        t_norm = unicodedata.normalize("NFC", t)
        clean_t = re.sub(r"<[^>]*>", "", t_norm).strip()
        clean_t = re.sub(r"^(?:[0-9]{1,2}[.)\]]\s*|[#*\-•]\s*)", "", clean_t).strip()

        if not clean_t or clean_t in seen:
            continue

        seen.add(clean_t)
        cleaned_titles.append(clean_t)

    # Ensure exactly 4 distinct headlines
    while len(cleaned_titles) < 4:
        fallback = cleaned_titles[0] if cleaned_titles else "പ്രധാന വാർത്തകൾ"
        cleaned_titles.append(f"{fallback} - കൂടുതൽ വിവരങ്ങൾ")

    content_norm = unicodedata.normalize("NFC", data.content)
    sanitized_content = sanitize_html(content_norm)
    if not sanitized_content:
        raise ValueError("Rewritten content cannot be empty.")

    return {
        "titles": cleaned_titles[:4],
        "content": sanitized_content,
    }


# ==========================================
# 3. Universal Critic & Refine Engine
# ==========================================

def execute_critic_pipeline(client, source_title: str, source_text: str, article_id: int) -> dict:
    """Executes Write -> Audit Critic -> Polish only if needed."""

    # -------------------------------------------------------------
    # PASS 1: Senior Newsdesk Rewriter (Deep Rewriting & Sandboxing)
    # -------------------------------------------------------------
    writer_prompt = (
        "You are an expert Senior Malayalam Newsdesk Rewriter (വാർത്താ പുനരാവിഷ്കർത്താവ്).\n"
        "Your mandate is NOT to proofread, edit, or mirror the source text. "
        "Your job is to read the raw facts and compose an original, publication-ready news dispatch in fresh Malayalam news prose (ലളിതവും ആധികാരികവുമായ പത്രശൈലി).\n"
        "The output must retain 100% of the underlying facts, numbers, quotes, and statements while being structurally and linguistically distinct from the source text.\n\n"
        
        "MANDATORY EDITORIAL INVARIANTS:\n\n"
        "1. DEEP RESTRUCTURING & PHRASE DIVERSITY (വാക്യഘടന പൂർണ്ണമായി മാറ്റിയെഴുതുക):\n"
        "   - Do not copy sentences or clauses verbatim. Never reuse 4 or more consecutive words from any source sentence (except for proper nouns, entity names, and exact numbers).\n"
        "   - Invert clause orders, vary sentence openings, and use fresh journalistic phrasing rather than shallow word-for-word synonym swapping.\n"
        "   - Consolidate fragmented, single-sentence paragraphs into 2 to 4 rich, cohesive HTML paragraphs (<p>). Do not mirror the source's chronological paragraph-by-paragraph layout. Do not use bullet points.\n\n"
        
        "2. AXIOMATIC SOURCE TRUTH (ZERO EXTERNAL FACT-CHECKING):\n"
        "   - Treat the provided source text as an absolute, isolated universe of truth.\n"
        "   - You are strictly forbidden from applying external real-world knowledge to verify, 'correct', fact-check, or alter ANY detail from the source.\n"
        "   - Every proper noun, designation, office, title, date, and historical claim in the source must be preserved exactly as presented, even if it contradicts real-world reality.\n\n"
        
        "3. PROPER NOUN & ACTOR COMPLETENESS (പേരുകൾ ഒഴിവാക്കരുത്):\n"
        "   - Every named individual, organization, and actor present in the source MUST be explicitly named in the output.\n"
        "   - Never drop a person's name or reduce them solely to their title. Include both title and name exactly as given.\n\n"
        
        "4. NUMERIC & MEASUREMENT PRECISION:\n"
        "   - Retain all numbers, counts, dates, years, scores, percentages, and metrics with 100% accuracy strictly in standard Arabic digits (e.g., 57, 40, 2026).\n"
        "   - Never convert digits into spelled-out Malayalam words.\n\n"
        
        "5. DATELINE PRESERVATION:\n"
        "   - If the source begins with a reporting location, preserve it strictly as an isolated bold prefix in Malayalam at the very start of the first paragraph (format: '<p><b>[Location]:</b> ...</p>'). Never absorb it into the sentence grammar.\n\n"
        
        "6. NATURAL STATEMENTS & FLOW:\n"
        "   - Integrate all reported statements, claims, and reactions smoothly into active journalistic flow without mechanical word-for-word translation or repetitive sentence endings.\n\n"
        
        "7. HEADLINES:\n"
        "   - Output exactly 4 distinct, engaging Malayalam headlines in 'titles' capturing different news angles.\n\n"
        
        f"Source Title: {source_title}\n\n"
        f"Source Content (with HTML tags):\n{source_text}"
    )

    logger.info(f"Article {article_id}: Generating deep rewrite...")
    resp_draft = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=writer_prompt,
        config=types.GenerateContentConfig(
            temperature=0.5,
            max_output_tokens=4000,
            response_mime_type="application/json",
            response_schema=RewriteDraft,
        ),
    )
    draft: RewriteDraft = resp_draft.parsed if resp_draft.parsed else RewriteDraft(**json.loads(resp_draft.text))

    # -------------------------------------------------------------
    # PASS 2: Universal Source-Fidelity Audit (NOT A REWRITER)
    # -------------------------------------------------------------
    critic_prompt = (
        "You are an adversarial newsroom copy-editor and source-fidelity auditor.\n"
        "Treat the ORIGINAL SOURCE as the sole, absolute universe of truth. Do NOT fact-check against real-world external knowledge.\n"
        "Compare the ORIGINAL SOURCE against the DRAFT REWRITE and inspect for these universal flaws:\n\n"
        "1. NUMERIC CORRUPTION OR WORD CONVERSION: Did the draft alter any number, date, or count, or convert Arabic digits to spelled-out words?\n"
        "2. DATELINE INTEGRITY: Did the draft absorb a location dateline into the grammar of the opening sentence instead of keeping it as an isolated prefix?\n"
        "3. PROPER NOUN & FACTUAL OMISSIONS: Did the draft drop or omit any named person, title, key entity, metric, or concrete factual event?\n"
        "4. EXTRANEOUS INJECTIONS & REAL-WORLD SUBSTITUTIONS: Did the draft introduce outside facts, or alter/replace ANY title, role, or designation from the source to match real-world reality?\n"
        "5. VERBATIM COPYING: Did the draft reproduce entire sentences or clauses word-for-word instead of freshly re-architecting the syntax in natural Malayalam?\n"
        "6. HEADLINE ACCURACY: Are the headlines overly generic, ambiguous, or misrepresenting the central news hook?\n\n"
        "DECISION RULE:\n"
        "- Set has_faults=true ONLY if there is an ungrounded external detail, a real factual error, a dropped name, or a corrupted number.\n"
        "- Do NOT flag fresh phrasing, sentence restructuring, or natural Malayalam clause order as a fault.\n"
        "- If the draft is completely faithful to facts with fresh syntax, set has_faults=false and leave specific_faults empty.\n\n"
        f"--- ORIGINAL SOURCE ---\n{source_text}\n\n"
        f"--- DRAFT HEADLINES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- DRAFT CONTENT ---\n{draft.content}"
    )

    logger.info(f"Article {article_id}: Running source-fidelity audit...")
    resp_critic = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=critic_prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=2000,
            response_mime_type="application/json",
            response_schema=CritiqueReport,
        ),
    )
    critic: CritiqueReport = resp_critic.parsed if resp_critic.parsed else CritiqueReport(**json.loads(resp_critic.text))

    # -------------------------------------------------------------
    # PASS 3: Factual Patch Only (NO UNDO LOOP)
    # -------------------------------------------------------------
    if critic.has_faults and critic.specific_faults:
        logger.info(f"Article {article_id}: Auditor flagged discrepancies ({critic.specific_faults}). Polishing...")

        polish_prompt = (
            "You are a news desk editor.\n"
            "Your task is to resolve ONLY the specific factual faults flagged by the auditor, while STRICTLY PROTECTING the draft's rewritten phrasing.\n\n"
            f"Auditor Flags to Fix:\n"
            f"{chr(10).join('- ' + f for f in critic.specific_faults)}\n\n"
            f"Draft Headlines for Reference:\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
            f"Initial Draft (PRIMARY BASELINE TO PRESERVE):\n{draft.content}\n\n"
            f"Original Source Content (FOR FACT-CHECKING REFERENCE ONLY):\n{source_text}\n\n"
            "RESOLUTION RULES:\n"
            "- Fix ONLY the specific flagged issues (e.g., restore a missing person name, correct a corrupted number, or purge an ungrounded fact).\n"
            "- DO NOT revert sentences or vocabulary back to the original source text.\n"
            "- PRESERVE the restructured, fresh Malayalam narrative style of the Initial Draft.\n"
            "- Retain and refine the 4 draft headlines so they remain punchy, accurate, and relevant."
        )

        resp_polish = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=polish_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4000,
                response_mime_type="application/json",
                response_schema=RewriteDraft,
            ),
        )
        final_draft: RewriteDraft = resp_polish.parsed if resp_polish.parsed else RewriteDraft(**json.loads(resp_polish.text))
    else:
        logger.info(f"Article {article_id}: Auditor passed cleanly. Finalizing.")
        final_draft = draft

    return verify_and_clean_output(final_draft)


def call_gemini_with_failover(source_title: str, source_text: str, article_id: int) -> dict:
    """Executes the pipeline with multi-key failover."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(client_args={"timeout": 120.0})
            )

            result = execute_critic_pipeline(client, source_title, source_text, article_id)
            result["key_used"] = f"{key_name} ({GEMINI_MODEL})"
            logger.info(f"✅ Successfully finished rewrite for article {article_id} using {key_name}")
            return result

        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            logger.warning(f"Gemini {key_name} failed on article {article_id}: {e}")

            if "timed out" in err_msg or "timeout" in err_msg:
                raise HTTPException(
                    status_code=504,
                    detail="Gemini API timed out during generation. Please try again.",
                )

            if "503" in err_msg or "unavailable" in err_msg or "high demand" in err_msg:
                raise HTTPException(
                    status_code=503,
                    detail="Google Gemini is currently experiencing high demand. Please try again in 1–2 minutes.",
                )

            if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                continue

            if "404" in err_msg or "not_found" in err_msg:
                raise HTTPException(
                    status_code=502,
                    detail=f"Model '{GEMINI_MODEL}' not found or unsupported.",
                )

            continue

    raise HTTPException(
        status_code=502,
        detail=f"All Gemini API keys failed during pipeline. Last error: {last_error}",
    )


# ==========================================
# 4. FastAPI Endpoint
# ==========================================

@router.post("/admin/rewrite/{article_id}")
def rewrite_article(article_id: int, admin=Depends(verify_admin)):
    with _in_flight_lock:
        if article_id in _in_flight_articles:
            raise HTTPException(
                status_code=409,
                detail="A rewrite for this article is already in progress.",
            )
        _in_flight_articles.add(article_id)

    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(status_code=404, detail="Article not found.")
        if article.status != "pending":
            raise HTTPException(
                status_code=400,
                detail="Only pending articles can be rewritten.",
            )

        raw_title = article.title
        raw_content = article.content
    finally:
        db.close()

    try:
        # Feeds the HTML string with tags preserved directly into the rewrite pipeline
        cleaned_content = clean_html_noise(raw_content)

        result = call_gemini_with_failover(
            source_title=raw_title,
            source_text=cleaned_content,
            article_id=article_id
        )

        return {
            "success": True,
            "article_id": article_id,
            "key_used": result.get("key_used"),
            "titles": result["titles"],
            "content": result["content"],
        }

    finally:
        with _in_flight_lock:
            _in_flight_articles.discard(article_id)