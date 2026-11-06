import os
import re
import html
import json
import logging
import threading
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

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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


class VerifiedRewriteResponse(BaseModel):
    audit_verification: List[str] = Field(
        description="Self-audit checklist: Extract all explicitly mentioned entities, statistics, and dates from the source, and verify zero external additions.",
    )
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct Malayalam headlines based strictly on the lead paragraph",
    )
    content: str = Field(
        description="Final publication-ready Malayalam article body formatted exclusively in safe HTML",
    )


def extract_first_paragraph(raw_html: str) -> str:
    """Extracts the first substantive paragraph to serve as factual lead for headlines."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    # Look for the first paragraph with real journalistic content (>= 15 words)
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text and len(text.split()) >= 15:
            return html.unescape(text)

    plain = html.unescape(soup.get_text(" ", strip=True))
    return plain[:600]


def sanitize_html(raw_html: str) -> str:
    """Sanitizes HTML content, stripping out disallowed tags and all tag attributes."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return "".join(str(c) for c in soup.contents).strip()


def verify_and_clean_output(data: VerifiedRewriteResponse) -> dict:
    """Sanitizes headlines (strips HTML and numbered bullets) and cleans HTML body."""
    cleaned_titles = []
    seen = set()

    for t in data.titles:
        # Strip any raw HTML tags
        clean_t = re.sub(r"<[^>]*>", "", t).strip()
        # Strip only list prefixes like '1. ', '2) ', '• ', '# ' without touching years/numbers
        clean_t = re.sub(r"^(?:[0-9]{1,2}[.)\]]\s*|[#*\-•]\s*)", "", clean_t).strip()

        if not clean_t or clean_t in seen:
            raise ValueError("All 4 headlines must be distinct and non-empty.")

        seen.add(clean_t)
        cleaned_titles.append(clean_t)

    sanitized_content = sanitize_html(data.content)
    if not sanitized_content:
        raise ValueError("Rewritten content cannot be empty.")

    return {
        "titles": cleaned_titles,
        "content": sanitized_content,
        "audit_notes": data.audit_verification,
    }


def call_gemini_with_failover(user_input: str, instructions: str, article_id: int) -> dict:
    """Single roundtrip generation with reflection and key failover."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            # 120,000 milliseconds = 120 seconds (gives Google ample time for Malayalam token generation)
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=120_000)
            )

            config = types.GenerateContentConfig(
                system_instruction=instructions,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                max_output_tokens=8000,
                response_mime_type="application/json",
                response_schema=VerifiedRewriteResponse,
            )

            logger.info(f"Article {article_id}: Executing verified rewrite using {key_name}...")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_input,
                config=config,
            )

            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                raise ValueError("Empty response received from Gemini.")

            finish_reason = str(getattr(candidate, "finish_reason", ""))

            if "SAFETY" in finish_reason:
                raise HTTPException(
                    status_code=422,
                    detail="Article was flagged by Gemini safety filters. Manual editing is required.",
                )

            if "MAX_TOKENS" in finish_reason:
                raise HTTPException(
                    status_code=422,
                    detail="Article exceeded maximum token limit. Source text is too long.",
                )

            if response.parsed:
                rewrite_obj = response.parsed
            else:
                rewrite_obj = VerifiedRewriteResponse(**json.loads(response.text))

            cleaned_result = verify_and_clean_output(rewrite_obj)
            cleaned_result["key_used"] = key_name

            logger.info(f"✅ Successfully completed verified rewrite for article {article_id} using {key_name}")
            return cleaned_result

        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            logger.warning(f"Gemini {key_name} failed on article {article_id}: {e}")

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
        lead_paragraph = extract_first_paragraph(raw_content)

        instructions = (
            "You are a Senior Chief Copy-Editor and Fact-Checker at a major Malayalam daily newsroom. "
            "Your objective is to produce a completely original, publication-grade Malayalam news article "
            "based strictly and exclusively on the provided source text.\n\n"
            "PHASE 1: FACTUAL AUDIT & INVENTORY (Fill 'audit_verification' FIRST):\n"
            "1. Extract and inventory every explicit named entity, office/designation, organization, and location.\n"
            "2. Extract every numerical figure, statistic, percentage, date, and time.\n"
            "3. Enforce the Zero-Inference Rule: Commit to using ONLY the specific titles, designations, and names "
            "present in the text. Never infer or substitute real-world proper names or unmentioned identities.\n"
            "4. Enforce Numeric Invariance: Commit to preserving all figures exactly as stated without converting exact numbers "
            "into estimates (e.g., do not add 'more than' / 'ഏകദേശം' / 'അധികം' unless explicitly present in the source).\n\n"
            "PHASE 2: HEADLINE GENERATION ('titles'):\n"
            "- Produce exactly 4 distinct, compelling Malayalam headlines.\n"
            "- Every headline must be derived strictly and exclusively from the factual core of the lead paragraph.\n"
            "- Vary the journalistic focus across headlines (e.g., action-oriented, outcome-oriented, statement-oriented) "
            "while maintaining 100% factual fidelity.\n\n"
            "PHASE 3: REWRITE THE ARTICLE BODY ('content'):\n"
            "- Journalistic Restructuring: Do not mirror the source's paragraph sequence or clause structure. "
            "Synthesize the verified facts into fresh, natural journalistic Malayalam prose (പത്രശൈലി).\n"
            "- Closed-World Constraint: Treat the provided source as the sole universe of truth. Never invent background history, "
            "speculative motives, press-conference Q&A context, emotional descriptions, or boilerplate clichés.\n"
            "- Preserve Full Scope: Do not condense into a brief summary. Maintain all original facts, attributions, and context.\n"
            "- HTML Formatting: Use only clean, semantic HTML tags: <p>, <b>, <i>, <ul>, <li>, <blockquote>. "
            "Do not include markdown code fences (```), heading tags, or HTML attributes."
        )

        user_input = (
            f"Original Title: {raw_title}\n\n"
            f"Lead Paragraph: {lead_paragraph}\n\n"
            f"Full Source Content:\n{raw_content}"
        )

        result = call_gemini_with_failover(user_input, instructions, article_id)

        return {
            "success": True,
            "article_id": article_id,
            "key_used": result.get("key_used"),
            "audit_notes": result.get("audit_notes"),
            "titles": result["titles"],
            "content": result["content"],
        }

    finally:
        with _in_flight_lock:
            _in_flight_articles.discard(article_id)