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
# 1. Pydantic Schemas for Hermetic Critic Flow
# ==========================================

class RewriteDraft(BaseModel):
    titles: List[str] = Field(min_length=4, max_length=4, description="4 distinct, engaging Malayalam headlines")
    content: str = Field(description="Rewritten Malayalam news article in HTML paragraphs")


class CritiqueReport(BaseModel):
    has_faults: bool = Field(description="True if ANY outside information, factual corruption, or major omission exists.")
    specific_faults: List[str] = Field(
        default_factory=list,
        description="Clear, actionable points of what needs fixing, especially unmentioned outside information."
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
    """Sanitizes headlines, normalizes Unicode glyphs, and cleans HTML body."""
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
# 3. Hermetic Critic & Refine Engine
# ==========================================

def execute_critic_pipeline(client, source_title: str, source_text: str, article_id: int) -> dict:
    """Executes Hermetic Write -> Leakage Audit -> Polish."""

    # -------------------------------------------------------------
    # PASS 1: Hermetic Draft (Zero Outside Memory)
    # -------------------------------------------------------------
    writer_prompt = (
        "You are an isolated text processing and restructuring engine. "
        "Your task is to rewrite the provided news article into fresh, original Malayalam prose (പത്രശൈലി) "
        "using ONLY the provided text.\n\n"
        "ABSOLUTE HERMETIC ISOLATION (ZERO OUTSIDE MEMORY):\n"
        "1. COMPLETE AMNESIA: You possess ZERO external memory of the real world. You do not know who any person is, "
        "what any organization does, or what past events took place beyond what is explicitly typed in the source text.\n"
        "2. ZERO OUTSIDE INJECTIONS: Do NOT add any title, description, history, relationship, party affiliation, "
        "or biographical context not written in the source, even if you recognize the name.\n"
        "3. PURE TEXT RE-SYNTHESIS: Reorganize and rewrite the provided facts from scratch into natural, readable HTML paragraphs (<p>). "
        "Do not mirror sentences 1-to-1, and never use bulleted lists.\n"
        "4. Output exactly 4 distinct Malayalam headlines in 'titles' using only facts from the text.\n\n"
        f"Source Title: {source_title}\n\n"
        f"Source Content:\n{source_text}"
    )

    logger.info(f"Article {article_id}: Generating hermetic draft...")
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
    # PASS 2: Adversarial Leakage & Fidelity Auditor
    # -------------------------------------------------------------
    critic_prompt = (
        "You are a strict, adversarial fact-checking auditor. "
        "Your sole task is to check if the DRAFT REWRITE accessed ANY outside knowledge not present in the SOURCE TEXT.\n\n"
        "AUDIT CHECKLIST:\n"
        "1. KNOWLEDGE LEAKAGE CHECK: Did the draft introduce ANY outside information, title, designation, party name, "
        "biographical detail, or background context that was NOT explicitly stated in the source text? "
        "(For example, if the source text said a person's name and the draft added an unmentioned political or professional title, this is an OUTSIDE INFORMATION VIOLATION).\n"
        "2. Factual Distortion: Are any numbers, statistics, dates, or proper nouns altered or misspelled?\n"
        "3. Omission of Nuance: Did the draft drop any important qualifying clauses, caveats, or balanced perspectives?\n"
        "4. Tone: Did the draft add subjective commentary (e.g. 'എന്നത് ശ്രദ്ധേയമാണ്') or dramatic intensifiers?\n\n"
        "If ANY outside information or discrepancy was introduced, set has_faults=true and explicitly state: "
        "'Remove unmentioned outside detail: [detail]' under specific_faults.\n"
        "If the draft contains strictly zero outside information and is faithful, set has_faults=false.\n\n"
        f"--- ORIGINAL SOURCE ---\n{source_text}\n\n"
        f"--- DRAFT HEADLINES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- DRAFT CONTENT ---\n{draft.content}"
    )

    logger.info(f"Article {article_id}: Running Leakage Audit...")
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
    # PASS 3: Refine & Polish (Strips any leaked memory)
    # -------------------------------------------------------------
    if critic.has_faults and critic.specific_faults:
        logger.info(f"Article {article_id}: Critic detected leakage/faults ({critic.specific_faults}). Polishing...")

        polish_prompt = (
            "You are a strict news copy-editor. "
            "Produce the final publication-ready version by eliminating every piece of outside information or flaw flagged by the auditor.\n\n"
            f"Flaws Flagged by Auditor:\n"
            f"{chr(10).join('- ' + f for f in critic.specific_faults)}\n\n"
            f"Original Source Content (SOLE SOURCE OF TRUTH):\n{source_text}\n\n"
            f"Initial Draft for Reference:\n{draft.content}\n\n"
            "Requirements:\n"
            "- Remove any outside fact, unmentioned title, or biographical detail flagged by the auditor.\n"
            "- Ensure 100% of the content is derived exclusively from the source text.\n"
            "- Write in clean, flowing Malayalam HTML paragraphs (<p>, <b>, <i>)."
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
        logger.info(f"Article {article_id}: Zero leakage detected. Finalizing.")
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