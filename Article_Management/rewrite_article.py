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

# Model and key configuration
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

# Concurrency lock to prevent duplicate rewrites on the same article
_in_flight_lock = threading.Lock()
_in_flight_articles = set()

ALLOWED_TAGS = {"p", "br", "b", "i", "strong", "em", "ul", "ol", "li", "blockquote"}


# Pydantic schema enforcing structured JSON output from Gemini
class RewriteResponse(BaseModel):
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct Malayalam headlines based strictly on the lead paragraph",
    )
    content: str = Field(
        description="Restructured and rewritten article body in safe HTML format"
    )


def extract_first_paragraph(raw_html: str) -> str:
    """Extracts the first paragraph to serve as the exclusive source for headlines."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    p = soup.find("p")
    if p:
        text = p.get_text(" ", strip=True)
        if text:
            return html.unescape(text)

    # Fallback to leading text if no <p> tag exists
    plain = html.unescape(soup.get_text(" ", strip=True))
    return plain[:500]


def sanitize_html(raw_html: str) -> str:
    """Sanitizes HTML content, stripping out disallowed tags and all tag attributes."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return "".join(str(c) for c in soup.contents).strip()


def verify_and_clean_output(data: RewriteResponse) -> dict:
    """Sanitizes titles (XSS prevention, bullet cleanup) and ensures body HTML safety."""
    cleaned_titles = []
    seen = set()

    for t in data.titles:
        # Strip HTML tags to eliminate XSS risks in admin dashboards
        clean_t = re.sub(r"<[^>]*>", "", t).strip()
        # Strip numbered prefixes (e.g., '1. ', '1) ') or markdown bullet artifacts
        clean_t = re.sub(r"^[0-9#*\-•.)\s]+", "", clean_t).strip()

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


def call_gemini_with_failover(user_input: str, instructions: str) -> dict:
    """Calls Gemini with structured outputs, low thinking level, and multi-key failover."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(api_key=api_key)

            config = types.GenerateContentConfig(
                system_instruction=instructions,
                temperature=0.2,
                # Low thinking level prevents reasoning tokens from exhausting max_output_tokens
                thinking_config=types.ThinkingConfig(thinking_level="low"),
                max_output_tokens=16000,
                response_mime_type="application/json",
                response_schema=RewriteResponse,
            )

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_input,
                config=config,
            )

            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                raise ValueError("Empty response received from Gemini.")

            finish_reason = str(getattr(candidate, "finish_reason", ""))

            # Stop immediately on safety blocks (flagged content will fail across all keys)
            if "SAFETY" in finish_reason:
                raise HTTPException(
                    status_code=422,
                    detail="Article was flagged by Gemini safety filters. Manual editing is required.",
                )

            # Check if output hit the token limit
            if "MAX_TOKENS" in finish_reason:
                raise HTTPException(
                    status_code=422,
                    detail="Article exceeded the maximum token limit. Source text is too long.",
                )

            # Parse structured response
            if response.parsed:
                rewrite_obj = response.parsed
            else:
                rewrite_obj = RewriteResponse(**json.loads(response.text))

            return verify_and_clean_output(rewrite_obj)

        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            logger.warning(f"Gemini {key_name} failed: {e}")

            # Rotate to next key on rate limits or quota exhaustion
            if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                continue

            # Abort immediately if model is missing or misconfigured
            if "404" in err_msg or "not_found" in err_msg:
                raise HTTPException(
                    status_code=502,
                    detail=f"Model '{GEMINI_MODEL}' not found or unsupported.",
                )

            continue

    raise HTTPException(
        status_code=502,
        detail=f"All Gemini API keys failed. Last error: {last_error}",
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
        # Close DB session early so connections aren't tied up during AI generation
        db.close()

    try:
        lead_paragraph = extract_first_paragraph(raw_content)

        instructions = (
            "You are a professional Malayalam news editor. Rewrite the given news article into publication-grade Malayalam.\n\n"
            "Core Editorial Requirements:\n"
            "1. Output exactly 4 distinct, engaging Malayalam headlines in 'titles'.\n"
            "2. Headlines MUST be strictly derived from the provided lead paragraph without hallucinating external facts.\n"
            "3. Restructure the article narrative: DO NOT preserve the source paragraph order or sentence-by-sentence structure. "
            "Synthesize and reorganize the flow into fresh, natural journalistic paragraphs.\n"
            "4. Strict Factual Accuracy: DO NOT invent facts, speculate, exaggerate, or omit important facts. "
            "Retain all original facts, numbers, dates, statistics, and named entities exactly as reported.\n"
            "5. Formatting: Return the body in 'content', formatted exclusively using safe HTML tags: "
            "<p>, <b>, <i>, <ul>, <li>, <blockquote>. Do not use markdown backticks or unsupported tags."
        )

        user_input = (
            f"Original Title: {raw_title}\n\n"
            f"Lead Paragraph: {lead_paragraph}\n\n"
            f"Full Article Content:\n{raw_content}"
        )

        result = call_gemini_with_failover(user_input, instructions)

        return {
            "success": True,
            "article_id": article_id,
            "titles": result["titles"],
            "content": result["content"],
        }

    finally:
        with _in_flight_lock:
            _in_flight_articles.discard(article_id)