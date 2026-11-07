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

# Model configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Multi-key failover configuration
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


# Schema enforcing Fact Extraction FIRST, followed by Fresh Article Composition
class VerifiedRewriteResponse(BaseModel):
    audit_passed: bool = Field(
        description="True confirming all facts and figures match the source with zero external hallucinations."
    )
    extracted_facts: List[str] = Field(
        description="Brief list of explicit core facts, names, figures, and attributions extracted from the text."
    )
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct, engaging Malayalam headlines derived strictly from the core news lead."
    )
    content: str = Field(
        description="Completely original Malayalam news body written strictly using the extracted facts in flowing HTML paragraphs."
    )


def clean_html_noise(raw_html: str) -> str:
    """Removes scripts, styles, iframes, and non-content noise while preserving source text."""
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
    """Sanitizes headlines, normalizes Unicode glyphs, and cleans HTML body."""
    cleaned_titles = []
    seen = set()

    for t in data.titles:
        # Normalize Unicode to fix fragmented Malayalam vowel signs
        t_norm = unicodedata.normalize("NFC", t)
        clean_t = re.sub(r"<[^>]*>", "", t_norm).strip()
        # Strip only list prefixes (e.g., '1. ', '2) ', '• ') without touching numbers/years
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
        "extracted_facts": data.extracted_facts,
    }


def call_gemini_with_failover(prompt_payload: str, article_id: int) -> dict:
    """Fast, single-roundtrip rewrite with explicit socket timeout."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            # Explicit 120s transport timeout avoids socket drops
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    client_args={"timeout": 120.0}
                )
            )

            config = types.GenerateContentConfig(
                temperature=0.2,  # 0.2 provides creative phrasing without factual drift
                max_output_tokens=6000,
                response_mime_type="application/json",
                response_schema=VerifiedRewriteResponse,
            )

            logger.info(f"Article {article_id}: Executing rewrite with {GEMINI_MODEL} using {key_name}...")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt_payload,
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
                    detail="Gemini API read timed out. Google took too long to generate the article. Please try again.",
                )

            if "503" in err_msg or "unavailable" in err_msg or "high demand" in err_msg:
                raise HTTPException(
                    status_code=503,
                    detail="Google Gemini is currently experiencing high demand. Please try again in 1–2 minutes.",
                )

            # Quota exhausted: try next key
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

        prompt_payload = (
            "You are a Senior Chief Copy-Editor at a prestigious Malayalam newspaper desk. "
            "Your objective is to produce a completely original, publication-grade Malayalam news dispatch "
            "based strictly and exclusively on the verified facts of the provided source text.\n\n"
            "TWO-STAGE COMPOSITION PROCESS:\n"
            "STAGE 1: FACTUAL INVENTORY ('extracted_facts')\n"
            "- Extract and list the core factual points, named entities, proper names, statistics, dates, and official quotes.\n"
            "- Strict Proper Noun Rule: Verify every proper name character-by-character. Do NOT alter, abbreviate, or add suffixes to real-world names (e.g., 'നരേന്ദ്ര മോദി' must remain exactly 'നരേന്ദ്ര മോദി', never alter with suffixes like 'നരേന്ദ്രപൂർ').\n"
            "- Closed-World Rule: Extract ONLY facts present in the text. Never infer or introduce outside facts.\n\n"
            "STAGE 2: ORIGINAL NEWS COMPOSITION ('content')\n"
            "- Put the source text's sentences away. Using ONLY the raw facts in 'extracted_facts', compose a fresh, authoritative news report from scratch.\n"
            "- Zero Verbatim Copying: Do NOT follow the source text sentence-by-sentence or merely substitute synonyms. Synthesize and re-architect the flow into natural, professional Malayalam newspaper prose (പത്രശൈലി).\n"
            "- No Artificial Lists: The body must flow exclusively in rich, narrative HTML paragraphs (<p>). Do not convert spoken remarks or allegations into bulleted lists.\n"
            "- Numeric Invariance: Preserve all numbers, counts, and dates with 100% precision without converting exact figures into approximations.\n\n"
            "OUTPUT SPECIFICATIONS:\n"
            "- Set audit_passed to true.\n"
            "- Output 4 distinct Malayalam headlines in 'titles' grounded in the lead news.\n"
            "- Output rewritten body in 'content' using safe HTML: <p>, <b>, <i>, <blockquote>.\n\n"
            f"Original Title: {raw_title}\n\n"
            f"Lead News: {lead_paragraph}\n\n"
            f"Full Source Content:\n{cleaned_content}"
        )

        result = call_gemini_with_failover(prompt_payload, article_id)

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