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

# Configured model
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Configure available keys
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


# Fast schema: Boolean audit flag eliminates slow token generation
class VerifiedRewriteResponse(BaseModel):
    audit_passed: bool = Field(
        description="True confirming all facts/numbers match source and zero external names or speculative claims are added.",
    )
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct Malayalam headlines based strictly on the lead paragraph",
    )
    content: str = Field(
        description="Final publication-ready Malayalam article body formatted exclusively in safe HTML",
    )


def clean_html_noise(raw_html: str) -> str:
    """Removes scripts, styles, and iframe noise while preserving all article HTML."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav", "svg"]):
        tag.decompose()
    return str(soup)


def extract_first_paragraph(raw_html: str) -> str:
    """Extracts first substantive paragraph to serve as factual lead for headlines."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

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
        clean_t = re.sub(r"<[^>]*>", "", t).strip()
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
    }


def call_gemini_with_failover(user_input: str, instructions: str, article_id: int) -> dict:
    """Fast, single-roundtrip rewrite."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(api_key=api_key)

            config = types.GenerateContentConfig(
                system_instruction=instructions,
                temperature=0.0,
                max_output_tokens=6000,
                response_mime_type="application/json",
                response_schema=VerifiedRewriteResponse,
            )

            logger.info(f"Article {article_id}: Executing rewrite with {GEMINI_MODEL} using {key_name}...")
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
            cleaned_result["key_used"] = f"{key_name} ({GEMINI_MODEL})"

            logger.info(f"✅ Successfully completed rewrite for article {article_id} using {key_name}")
            return cleaned_result

        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            logger.warning(f"Gemini {key_name} failed on article {article_id}: {e}")

            if "timed out" in err_msg or "timeout" in err_msg:
                raise HTTPException(
                    status_code=504,
                    detail="Gemini API timed out generating the article. Please try again.",
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
        cleaned_content = clean_html_noise(raw_content)

        instructions = (
            "You are a Senior Chief Copy-Editor and Fact-Checker at a major Malayalam daily newsroom. "
            "Your objective is to produce a completely original, publication-grade Malayalam news article "
            "based strictly and exclusively on the provided source text.\n\n"
            "CRITICAL FACTUAL RULES:\n"
            "1. Zero-Inference Rule: Use ONLY the specific designations, titles, and names present in the text. "
            "Never infer or insert real-world proper names or unmentioned identities (e.g. if the text mentions a title/office, do not substitute an individual's name).\n"
            "2. Numeric Invariance: Preserve all numbers, statistics, percentages, and dates with 100% precision. "
            "Never convert exact numbers into estimates (do not add 'more than' / 'ഏകദേശം' / 'അധികം').\n"
            "3. Closed-World Constraint: Treat the source as the only facts that exist. Never invent background history, "
            "press Q&A context ('in response to questions'), or boilerplate clichés.\n\n"
            "HEADLINES & REWRITE:\n"
            "- Set audit_passed to true.\n"
            "- Generate exactly 4 distinct, compelling Malayalam headlines in 'titles' based on the lead paragraph.\n"
            "- In 'content', synthesize and restructure the article into fresh journalistic Malayalam prose (പത്രശൈലി) without mirroring sentence order.\n"
            "- Format exclusively in HTML: <p>, <b>, <i>, <ul>, <li>, <blockquote>."
        )

        user_input = (
            f"Original Title: {raw_title}\n\n"
            f"Lead Paragraph: {lead_paragraph}\n\n"
            f"Full Source Content:\n{cleaned_content}"
        )

        result = call_gemini_with_failover(user_input, instructions, article_id)

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