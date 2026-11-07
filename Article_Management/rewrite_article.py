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
    audit_passed: bool = Field(
        description="True confirming all facts and numbers match source text with zero outside additions.",
    )
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct Malayalam headlines based on the lead news facts",
    )
    content: str = Field(
        description="Rewritten Malayalam news article formatted in safe HTML using <p>, <b>, <i>, <ul>, <li>",
    )


def clean_html_noise(raw_html: str) -> str:
    """Removes scripts, styles, and iframe noise while preserving news content."""
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


def call_gemini_with_failover(prompt_payload: str, article_id: int) -> dict:
    """Calls Gemini with structured outputs, fast execution, and transparent error reporting."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(api_key=api_key)

            config = types.GenerateContentConfig(
                temperature=0.2,  # 0.2 gives linguistic flexibility to restructure without hallucinating
                max_output_tokens=6000,
                response_mime_type="application/json",
                response_schema=VerifiedRewriteResponse,
            )

            logger.info(f"Article {article_id}: Sending rewrite request to {GEMINI_MODEL} via {key_name}...")
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

            # If quota exhausted (429), try next key
            if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                continue

            # Model not found
            if "404" in err_msg or "not_found" in err_msg:
                raise HTTPException(
                    status_code=502,
                    detail=f"Model '{GEMINI_MODEL}' not found or unsupported.",
                )

            # If it's truly a 503 from Google
            if "503" in err_msg or "unavailable" in err_msg:
                continue

            continue

    # Surface the real underlying error so you can see it in UI
    raise HTTPException(
        status_code=502,
        detail=f"Rewrite failed across configured keys. Error: {last_error}",
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

        # Unified concise prompt (identical structure to the successful standalone test)
        prompt_payload = (
            "You are a Senior Chief Copy-Editor at a leading Malayalam daily news organization. "
            "Your objective is to produce an entirely original, publication-grade Malayalam news report "
            "based strictly and exclusively on the provided source text.\n\n"
            "MANDATORY STRUCTURAL RE-SYNTHESIS (STOP VERBATIM COPYING):\n"
            "1. NO CHRONOLOGICAL MIRRORING: Under no circumstances should you reproduce the source text sentence-by-sentence. "
            "Do not merely swap synonyms or append reporting tags (such as 'വ്യക്തമാക്കി' or 'ചോദിച്ചു') to existing sentences.\n"
            "2. THEMATIC GROUPING ARCHITECTURE: Restructure the narrative into logical news themes rather than the source's order:\n"
            "   - Lead Overview: Synthesize the primary development, central incident, or overarching claim into an active opening.\n"
            "   - Core Evidence & Data: Consolidate all metrics, figures, statistics, specific allegations, and concrete dates into a dedicated, cohesive section.\n"
            "   - Procedural Context & Perspectives: Group background history, procedural findings, official statements, and counter-arguments together.\n"
            "   - Resolution / Forward Status: Conclude with the current status, pending investigations, demands, or scheduled next steps.\n"
            "3. AUTHENTIC JOURNALISTIC PROSE: Write natural, publication-grade Malayalam newspaper prose (പത്രശൈലി). "
            "Combine fragmented sentences into clean, authoritative narrative paragraphs.\n"
            "4. NO ARTIFICIAL FORMATTING: Deliver the body strictly in flowing narrative paragraphs (<p>). Do not convert spoken statements into bullet lists.\n\n"
            "STRICT FACTUAL FIDELITY (ZERO HALLUCINATIONS):\n"
            "1. CLOSED-WORLD RULE: Treat the provided text as the sole universe of truth. Never invent outside history, "
            "unmentioned individuals, speculative causes, motives, or boilerplate filler not directly asserted in the text.\n"
            "2. ZERO INFERENCE: Use only the exact designations, titles, organizations, and names present in the text.\n"
            "3. NUMERIC INVARIANCE: Every number, metric, percentage, date, and statistic must remain 100% exact. "
            "Never convert exact figures into approximations (e.g., do not add 'ഏകദേശം' / 'അധികം' unless explicitly present in the source).\n\n"
            "OUTPUT SPECIFICATIONS:\n"
            "- Set audit_passed to true.\n"
            "- Generate exactly 4 distinct, compelling Malayalam headlines in 'titles' derived from the lead facts.\n"
            "- Return the article body in 'content' formatted strictly in clean HTML: <p>, <b>, <i>, <blockquote>.\n\n"
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