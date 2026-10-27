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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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
        description="Exactly 4 distinct Malayalam headlines based strictly on the lead paragraph",
    )
    content: str = Field(
        description="Restructured and rewritten article body in safe HTML format"
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
    """Calls configured Gemini API keys with structured output, timeout, and failover."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            # 25-second client timeout ensures Google never hangs your server
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=25_000)
            )

            config = types.GenerateContentConfig(
                system_instruction=instructions,
                temperature=0.2,
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

            # Handle safety block immediately without cycling other keys
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

            # Log the successful key for easy monitoring
            logger.info(f"✅ Successfully rewrote article {article_id} using {key_name} ({GEMINI_MODEL})")
            return cleaned_result

        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            logger.warning(f"Gemini {key_name} failed on article {article_id}: {e}")

            # 503 means Google's servers for this model are overloaded
            if "503" in err_msg or "unavailable" in err_msg or "high demand" in err_msg:
                raise HTTPException(
                    status_code=503,
                    detail="Google Gemini is currently experiencing high demand. Please try again in 1–2 minutes.",
                )

            # If rate limited (429), try next key
            if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                continue

            # If model name is invalid, fail fast
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
            "You are a seasoned Chief Sub-Editor at a leading Malayalam daily. "
            "Your objective is to produce a completely original, publication-grade Malayalam news article "
            "from the provided source material.\n\n"
            "CRITICAL REWRITING RULES (ORIGINALITY & STRUCTURE):\n"
            "1. NO SENTENCE-BY-SENTENCE PARAPHRASING: Under no circumstances should you mirror the source's "
            "sentence order, clause arrangement, or paragraph sequence. Do not simply swap synonyms in place. "
            "Internalize the facts and write a fresh report from scratch in authentic Malayalam journalistic prose (പത്രശൈലി).\n"
            "2. FULL ARTICLE DEPTH (NOT A SUMMARY): This must be a comprehensive, full-length news report. "
            "Do NOT summarize, condense, or omit details. Retain all background context, timeline of events, "
            "official statements, and nuances—restructured into an engaging, cohesive narrative.\n"
            "3. INVERTED PYRAMID ARCHITECTURE: Re-architect the story logically:\n"
            "   - Lead with the most impactful developments (Who, What, Where, When, Why, and How).\n"
            "   - Follow with supporting evidence, chronological context, and background.\n"
            "   - Conclude with ongoing investigations, official statements, or next steps.\n"
            "4. NATURAL MALAYALAM JOURNALISTIC DICTION:\n"
            "   - Avoid stiff, robotic, or machine-translated Malayalam.\n"
            "   - Break long, tangled sentences into punchy, clear journalistic sentences.\n"
            "   - Use authentic Malayalam news connectives (e.g., അതേസമയം, ഇതുസംബന്ധിച്ച്, പ്രാഥമിക വിവരങ്ങൾ പ്രകാരം, റിപ്പോർട്ടുകൾ സൂചിപ്പിക്കുന്നു).\n"
            "5. STRICT FACTUAL FIDELITY (NO HALLUCINATIONS):\n"
            "   - Never invent facts, motives, claims, or speculation.\n"
            "   - Every name, designation, date, statistic, number, location, and legal term must match the source with 100% precision.\n\n"
            "HEADLINE REQUIREMENTS:\n"
            "- Provide exactly 4 unique, impactful Malayalam headlines in 'titles'.\n"
            "- Every headline must be grounded strictly in the core lead facts of the story.\n"
            "- Headlines must vary in angle (e.g., direct impact, action-oriented, contextual) but avoid sensational clickbait.\n\n"
            "FORMATTING REQUIREMENTS:\n"
            "- Return the article body in 'content' exclusively formatted using clean HTML tags: <p>, <b>, <i>, <ul>, <li>, <blockquote>.\n"
            "- Do not use markdown backticks (```), <h1>/<h2> tags, or unsupported attributes."
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