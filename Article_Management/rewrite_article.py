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

# Model configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Configure available API keys
GEMINI_KEYS = [
    ("KEY_1", os.getenv("GEMINI_API_KEY_1")),
    ("KEY_2", os.getenv("GEMINI_API_KEY_2")),
    ("KEY_3", os.getenv("GEMINI_API_KEY_3")),
    ("KEY_4", os.getenv("GEMINI_API_KEY_4")),
    ("KEY_5", os.getenv("GEMINI_API_KEY_5")),
    ("KEY_6", os.getenv("GEMINI_API_KEY_6")),
]
GEMINI_KEYS = [(name, key) for name, key in GEMINI_KEYS if key]

# Thread safety lock for in-flight requests
_in_flight_lock = threading.Lock()
_in_flight_articles = set()

ALLOWED_TAGS = {"p", "br", "b", "i", "strong", "em", "ul", "ol", "li", "blockquote"}


# Pydantic schema for structured output
class RewriteResponse(BaseModel):
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct, engaging Malayalam headlines capturing different news angles.",
    )
    content: str = Field(
        description="Restructured and rewritten Malayalam news article in clean HTML paragraphs (<p>)."
    )


def extract_first_paragraph(raw_html: str) -> str:
    """Extracts the first paragraph to serve as the exclusive factual source for headlines."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    p = soup.find("p")
    if p:
        text = p.get_text(" ", strip=True)
        if text:
            return html.unescape(text)

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
    """Sanitizes headlines (strips HTML and bullet artifacts) and cleans HTML body."""
    cleaned_titles = []
    seen = set()

    for t in data.titles:
        clean_t = re.sub(r"<[^>]*>", "", t).strip()
        clean_t = re.sub(r"^[0-9#*\-•.)\s]+", "", clean_t).strip()

        if not clean_t or clean_t in seen:
            continue

        seen.add(clean_t)
        cleaned_titles.append(clean_t)

    while len(cleaned_titles) < 4:
        fallback = cleaned_titles[0] if cleaned_titles else "പ്രധാന വാർത്തകൾ"
        cleaned_titles.append(f"{fallback} - കൂടുതൽ വിവരങ്ങൾ")

    sanitized_content = sanitize_html(data.content)
    if not sanitized_content:
        raise ValueError("Rewritten content cannot be empty.")

    return {
        "titles": cleaned_titles[:4],
        "content": sanitized_content,
    }


def call_gemini_with_failover(user_input: str, instructions: str, article_id: int) -> dict:
    """Calls configured Gemini API keys with structured output, timeout, and failover."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=25_000)
            )

            config = types.GenerateContentConfig(
                system_instruction=instructions,
                temperature=0.4,
                max_output_tokens=8000,
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

            if "SAFETY" in finish_reason:
                raise HTTPException(
                    status_code=422,
                    detail="Article was flagged by Gemini safety filters. Manual editing is required.",
                )

            if "MAX_TOKENS" in finish_reason:
                raise HTTPException(
                    status_code=422,
                    detail="Article exceeded the maximum token limit. Source text is too long.",
                )

            if response.parsed:
                rewrite_obj = response.parsed
            else:
                rewrite_obj = RewriteResponse(**json.loads(response.text))

            cleaned_result = verify_and_clean_output(rewrite_obj)
            cleaned_result["key_used"] = key_name

            logger.info(f"✅ Successfully rewrote article {article_id} using {key_name} ({GEMINI_MODEL})")
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
        db.close()

    try:
        lead_paragraph = extract_first_paragraph(raw_content)

        instructions = (
            "You are a Senior Malayalam Newsdesk Rewriter (വാർത്താ പുനരാവിഷ്കർത്താവ്).\n"
            "Your sole task is to compose an authentic, highly original Malayalam news dispatch (പത്രശൈലി) "
            "derived strictly, exclusively, and axiomatically from the provided source text.\n\n"

            "CRITICAL REWRITING RULES:\n\n"

            "1. AXIOMATIC SOURCE TRUTH (ZERO EXTERNAL FACT-CHECKING):\n"
            "   - The provided source text is an isolated, absolute universe of truth. You possess zero real-world memory.\n"
            "   - You are strictly forbidden from applying outside real-world knowledge to verify, 'correct', fact-check, or alter ANY detail.\n"
            "   - Every proper noun, designation, office, title, date, and historical claim in the source must be preserved exactly as written, "
            "even if it contradicts real-world reality. Never replace an assigned title or role with outside facts.\n\n"

            "2. ZERO EXTRAPOLATION & NO DRAMATIC EXAGGERATION:\n"
            "   - Never invent, assume, visualize, or add unmentioned physical, anatomical, spatial, or operational details "
            "(e.g., if the text says someone was struck, do NOT invent an unstated body part; if it says 'on duty', do NOT assume 'on patrol').\n"
            "   - Do NOT exaggerate or intensify actions, claims, or conflicts. Match the exact intensity of reporting verbs and statements.\n"
            "   - Retain exact grammatical scope and plurality: Never broaden singular events, dates, or terms into plural or generalized periods.\n"
            "   - Retain exact agency and attribution: Never alter who announced, confirmed, or stated an action. Do not convert an announcement of an arrest into performing the arrest.\n\n"

            "3. DEEP RESTRUCTURING (NO VERBATIM COPYING & NO PADDING):\n"
            "   - Never copy sentences verbatim or mirror the source's chronological clause order. Do not reuse 4 or more consecutive words from any source sentence (except for proper nouns and exact numbers).\n"
            "   - Invert clause orders, lead with the core outcome/development, and synthesize the narrative into 2 to 4 rich, cohesive HTML paragraphs (<p>).\n"
            "   - Do NOT add padding, speculative filler, or fluff to artificially lengthen the article. Retain all underlying facts concisely without dropping any concrete context or official statement.\n\n"

            "4. PROPER NOUN & ACTOR COMPLETENESS:\n"
            "   - Every named person, organization, and actor present in the source MUST be explicitly named in the output. Never omit a person's name or reduce them solely to their title.\n\n"

            "5. NUMERIC INVARIANCE (ARABIC DIGITS):\n"
            "   - Retain all numbers, counts, dates, years, scores, percentages, and metrics with 100% precision strictly in standard Arabic digits (e.g., 57, 40, 2026). Never convert digits into spelled-out Malayalam words.\n\n"

            "6. DATELINE PRESERVATION:\n"
            "   - If the source begins with a reporting location, preserve it strictly as an isolated bold prefix in Malayalam at the very start of the first paragraph (format: '<p><b>[Location]:</b> ...</p>'). Never absorb it into the sentence grammar.\n\n"

            "HEADLINE REQUIREMENTS:\n"
            "- Provide exactly 4 unique, impactful Malayalam headlines in 'titles'.\n"
            "- Ground all headlines strictly in the core lead facts of the story. Include key actor names where appropriate.\n"
            "- Vary the editorial angles without sensational clickbait or terminological exaggeration.\n\n"

            "FORMATTING REQUIREMENTS:\n"
            "- Return the article body in 'content' exclusively formatted using clean HTML tags: <p>, <b>, <i>, <ul>, <li>, <blockquote>.\n"
            "- Do not use markdown backticks (```), <h1>/<h2> tags, or tag attributes."
        )

        user_input = (
            f"Original Title: {raw_title}\n\n"
            f"Lead Paragraph: {lead_paragraph}\n\n"
            f"Full Article Content:\n{raw_content}"
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