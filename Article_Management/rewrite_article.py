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
# 1. Pydantic Schemas for Containment Flow
# ==========================================

class RewriteDraft(BaseModel):
    titles: List[str] = Field(min_length=4, max_length=4, description="4 distinct, engaging Malayalam headlines")
    content: str = Field(description="Rewritten Malayalam news article in HTML paragraphs")


class CritiqueReport(BaseModel):
    has_faults: bool = Field(description="True if ANY outside information, unsupported claim, or factual distortion exists.")
    specific_faults: List[str] = Field(
        default_factory=list,
        description="Clear list of specific ungrounded details or errors that must be removed/corrected."
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
# 3. Containment Critic & Refine Engine
# ==========================================

def execute_critic_pipeline(client, source_title: str, source_text: str, article_id: int) -> dict:
    """Executes Hermetic Write -> Factual Containment Audit -> Polish."""

    # -------------------------------------------------------------
    # PASS 1: Strict Hermetic Re-Synthesis
    # -------------------------------------------------------------
    writer_prompt = (
        "You are an isolated text restructuring engine. "
        "Your sole task is to rewrite the provided source text into fresh, publication-grade Malayalam news prose (പത്രശൈലി) "
        "using EXCLUSIVELY the facts, entities, and statements present in the source text.\n\n"
        "STRICT CLOSED-WORLD CONSTRAINT:\n"
        "1. COMPLETE TEXTUAL CONTAINMENT: The provided text is the entire universe of truth. "
        "You possess ZERO external knowledge of real-world history, people, organizations, science, or events. "
        "Every entity, relationship, context, number, or statement in your output must be directly supported by the provided text.\n"
        "2. ZERO EXTRAPOLATION: Never add any fact, descriptor, context, cause, motive, or background detail that is not explicitly stated, "
        "even if it is universally true in the real world.\n"
        "3. RESTRUCTURE FROM SCRATCH: Compose fresh narrative prose without copying the source sentence-by-sentence. "
        "Organize the facts into clean, flowing HTML paragraphs (<p>). Do not use bulleted lists.\n"
        "4. HEADLINES: Output exactly 4 distinct, engaging Malayalam headlines in 'titles' grounded strictly in the provided text.\n\n"
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
    # PASS 2: Universal Factual Entailment Audit
    # -------------------------------------------------------------
    critic_prompt = (
        "You are a strict, adversarial fact-checking auditor. "
        "Your task is to conduct a strict factual entailment check: verify whether EVERY single claim, entity, "
        "number, context, and descriptor in the REWRITTEN DRAFT is strictly derived from the SOURCE TEXT.\n\n"
        "AUDIT CRITERIA:\n"
        "1. Extraneous Information Check: Does the draft contain ANY word, entity, descriptor, historical context, "
        "or factual claim that cannot be directly found in the source text? "
        "(If any detail in the draft relies on outside real-world knowledge rather than the source text, mark it as an EXTRANEOUS INFORMATION VIOLATION).\n"
        "2. Factual & Numeric Precision: Were any numbers, dates, statistics, or proper nouns altered, approximated, or misspelled?\n"
        "3. Omission of Balance: Did the draft drop any important qualifying clauses, caveats, or balancing perspectives?\n"
        "4. Tone: Did the draft add subjective commentary, metanarrative filler, or unquoted dramatic intensifiers?\n\n"
        "If the draft contains ANY extraneous information, unsupported claims, or factual discrepancies, "
        "set has_faults=true and list the exact ungrounded details under specific_faults: 'Remove unsupported detail: [detail]'.\n"
        "If every single claim in the draft is 100% supported by the source text, set has_faults=false.\n\n"
        f"--- ORIGINAL SOURCE ---\n{source_text}\n\n"
        f"--- DRAFT HEADLINES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- DRAFT CONTENT ---\n{draft.content}"
    )

    logger.info(f"Article {article_id}: Running Factual Entailment Audit...")
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
    # PASS 3: Refine & Polish (Strips any external data)
    # -------------------------------------------------------------
    if critic.has_faults and critic.specific_faults:
        logger.info(f"Article {article_id}: Auditor detected extraneous data/faults ({critic.specific_faults}). Polishing...")

        polish_prompt = (
            "You are a strict news copy-editor. "
            "Produce the final publication-ready version by eliminating every piece of extraneous information or flaw flagged by the auditor.\n\n"
            f"Flaws Flagged by Auditor:\n"
            f"{chr(10).join('- ' + f for f in critic.specific_faults)}\n\n"
            f"Original Source Content (SOLE SOURCE OF TRUTH):\n{source_text}\n\n"
            f"Initial Draft for Reference:\n{draft.content}\n\n"
            "Requirements:\n"
            "- Strictly purge every extraneous detail, ungrounded descriptor, or outside fact flagged by the auditor.\n"
            "- Ensure 100% of the information is derived solely and directly from the source text.\n"
            "- Maintain clean, flowing Malayalam newspaper prose (പത്രശൈലി) in HTML paragraphs (<p>, <b>, <i>)."
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
        logger.info(f"Article {article_id}: Zero extraneous information detected. Finalizing.")
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