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
        description="4 distinct, engaging Malayalam headlines capturing both the core action/justification and key conflict/context."
    )
    content: str = Field(
        description="Complete Malayalam news article in HTML paragraphs (<p>) covering every factual statement from the source with exact semantic fidelity."
    )


class CritiqueReport(BaseModel):
    has_faults: bool = Field(
        description="True if ANY factual omission, polarity shift, directional distortion, outside addition, or verbatim copying exists."
    )
    specific_faults: List[str] = Field(
        default_factory=list,
        description="Actionable points of what needs fixing."
    )


# ==========================================
# 2. Text and HTML Sanitization
# ==========================================

def clean_html_noise(raw_html: str) -> str:
    """Removes scripts, styles, and non-content noise while preserving article text."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav", "svg"]):
        tag.decompose()
    return str(soup)


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
            raise ValueError("All 4 headlines must be distinct and non-empty.")

        seen.add(clean_t)
        cleaned_titles.append(clean_t)

    content_norm = unicodedata.normalize("NFC", data.content)
    sanitized_content = sanitize_html(content_norm)
    if not sanitized_content:
        raise ValueError("Rewritten content cannot be empty.")

    return {
        "titles": cleaned_titles,
        "content": sanitized_content,
    }


# ==========================================
# 3. Universal Critic & Refine Engine
# ==========================================

def execute_critic_pipeline(client, source_title: str, source_text: str, article_id: int) -> dict:
    """Executes Write -> Audit Critic -> Polish only if needed."""

    # -------------------------------------------------------------
    # PASS 1: Generic Calibrated Synthesis
    # -------------------------------------------------------------
    writer_prompt = (
        "You are an expert news desk copy-editor.\n"
        "Your task is to produce a fresh, publication-ready news dispatch in authentic, standard Malayalam newspaper prose (ലളിതമായ പത്രശൈലി) "
        "derived strictly and exclusively from the provided source text.\n\n"
        "MANDATORY EDITORIAL INVARIANTS:\n"
        "1. SYNTACTIC TRANSFORMATION: Do not copy original sentences word-for-word. Combine related points, restructure clause order, "
        "and present the narrative in fresh syntax. Write in clean HTML paragraphs (<p>). Never use bulleted lists.\n"
        "2. SEMANTIC & POLARITY CONGRUENCE: Match the exact semantic scope, polarity, and degree of certainty of every source claim:\n"
        "   - Negative boundaries must remain negative boundaries (do not convert a negative boundary such as 'will not undermine X' into a positive affirmative pledge such as 'will strictly enforce X').\n"
        "   - Do not attach unstated operational scopes or sub-domains not present in the wire.\n"
        "   - Preserve directional and functional terms with 100% precision (do not invert an increase into a decrease, an extension into a reduction, or a defense into passive consent).\n"
        "3. TOTAL FACTUAL COMPLETENESS (ZERO OMISSIONS): Every concrete data point in the source—including all proper nouns, individual names, organizations, "
        "counts, metrics, calendar years, dates, timeframes, and specific points of friction or justification—must be preserved.\n"
        "4. CLOSED-WORLD RULE (ZERO OUTSIDE INJECTIONS): You possess zero external memory of the world. Treat the provided text as the sole universe of truth. "
        "Never add unmentioned personal titles, affiliations, background history, subjective adjectives, or speculative forecasts.\n"
        "5. DUAL-HOOK HEADLINES: Output exactly 4 distinct, engaging Malayalam headlines in 'titles'. Headlines must pair the primary action/justification with "
        "the core conflict, impact, or specific context, avoiding bland, passive, single-topic summaries.\n\n"
        f"Source Title: {source_title}\n\n"
        f"Source Content:\n{source_text}"
    )

    logger.info(f"Article {article_id}: Generating draft...")
    resp_draft = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=writer_prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4000,
            response_mime_type="application/json",
            response_schema=RewriteDraft,
        ),
    )
    draft: RewriteDraft = resp_draft.parsed if resp_draft.parsed else RewriteDraft(**json.loads(resp_draft.text))

    # -------------------------------------------------------------
    # PASS 2: Universal Adversarial Critic Prompt
    # -------------------------------------------------------------
    critic_prompt = (
        "You are an adversarial newsroom fact-checker and senior copy-editor.\n"
        "Compare the ORIGINAL SOURCE against the DRAFT REWRITE and inspect for these universal flaws:\n\n"
        "1. POLARITY, SCOPE & DIRECTIONAL SHIFTS:\n"
        "   - Did the draft convert a negative boundary statement into an affirmative promise?\n"
        "   - Did it attach unstated operational sub-domains or qualifiers absent from the source?\n"
        "   - Did it invert or distort any directional or functional term (e.g. confusing an extension with a reduction, or defense with passive agreement)?\n"
        "2. FACTUAL OMISSIONS: Did the draft drop or summarize away ANY named individual, entity, metric, figure, calendar year, timeframe, or specific point of justification/criticism?\n"
        "3. EXTRANEOUS INJECTIONS: Did the draft add unmentioned personal titles, external affiliations, unstated evaluative adjectives, or speculative forecasts?\n"
        "4. VERBATIM COPYING: Did the draft reproduce entire sentences or clauses word-for-word instead of freshly re-architecting the syntax?\n"
        "5. HEADLINE IMPACT: Are the headlines overly generic or missing the primary friction/justification?\n\n"
        "DECISION RULE:\n"
        "- If ANY of these flaws exist, set has_faults=true and list exact actionable fixes under specific_faults.\n"
        "- If the draft is freshly phrased, semantically congruent, completely faithful, and contains zero outside additions, set has_faults=false.\n\n"
        f"--- ORIGINAL SOURCE ---\n{source_text}\n\n"
        f"--- DRAFT HEADLINES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- DRAFT CONTENT ---\n{draft.content}"
    )

    logger.info(f"Article {article_id}: Running Audit evaluation...")
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
    # PASS 3: Universal Polish Prompt
    # -------------------------------------------------------------
    if critic.has_faults and critic.specific_faults:
        logger.info(f"Article {article_id}: Auditor flagged flaws ({critic.specific_faults}). Polishing final version...")

        polish_prompt = (
            "You are the Chief Editor at the Malayalam news desk.\n"
            "Produce the final publication-ready version by resolving every item flagged by the auditor:\n\n"
            f"Auditor Flags:\n"
            f"{chr(10).join('- ' + f for f in critic.specific_faults)}\n\n"
            f"Original Source Content (SOLE SOURCE OF TRUTH):\n{source_text}\n\n"
            f"Draft for Reference:\n{draft.content}\n\n"
            "Resolution Rules:\n"
            "- Correct all polarity or scope distortions back to the exact source meaning.\n"
            "- Restore any omitted entities, names, figures, years, or arguments flagged by the auditor.\n"
            "- Remove all unmentioned outside facts, titles, or subjective adjectives flagged by the auditor.\n"
            "- Ensure headlines capture both the primary action and key context/conflict.\n"
            "- Write in clean, standard Malayalam newspaper prose (ലളിതമായ പത്രശൈലി) in HTML paragraphs (<p>, <b>, <i>)."
        )

        resp_polish = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=polish_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
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