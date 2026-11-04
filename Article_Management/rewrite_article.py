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

_in_flight_lock = threading.Lock()
_in_flight_articles = set()

ALLOWED_TAGS = {"p", "br", "b", "i", "strong", "em", "ul", "ol", "li", "blockquote"}


# ==========================================
# 1. Pydantic Schemas for Multi-Stage Flow
# ==========================================

class RewriteDraft(BaseModel):
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description="Exactly 4 distinct Malayalam headlines based strictly on the lead facts",
    )
    content: str = Field(
        description="Rewritten HTML article body"
    )


class AuditReport(BaseModel):
    is_faithful: bool = Field(
        description="True ONLY if every entity, number, and statement in the rewrite is strictly derived from the source without outside additions."
    )
    unsupported_additions: List[str] = Field(
        default_factory=list,
        description="List of specific proper names, claims, or stock filler added that were not in the original text.",
    )
    numeric_issues: List[str] = Field(
        default_factory=list,
        description="List of numbers, dates, or statistics dropped, distorted (e.g. adding 'more than'), or invented.",
    )
    editorial_critique: str = Field(
        description="Specific instructions on how to reorganize the flow, fix narrative tone, or remove paraphrasing habits.",
    )


# ==========================================
# 2. HTML and Text Sanitization
# ==========================================

def extract_first_paragraph(raw_html: str) -> str:
    """Extracts first paragraph to serve as exclusive factual lead for headlines."""
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


def verify_and_clean_output(data: RewriteDraft) -> dict:
    """Sanitizes headlines and HTML content before sending to UI."""
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


# ==========================================
# 3. Multi-Stage Pipeline Functions
# ==========================================

def pass_1_generate_draft(client, source_title: str, lead_para: str, full_content: str) -> RewriteDraft:
    """Stage 1: Generates the initial draft at temperature 0.0."""
    writer_instructions = (
        "You are a professional Malayalam news journalist. Rewrite the provided source article into fresh, "
        "original journalistic Malayalam (പത്രശൈലി).\n\n"
        "RULES:\n"
        "1. Produce exactly 4 distinct Malayalam headlines based solely on the lead paragraph.\n"
        "2. Do not mirror sentence-by-sentence order of the source; restructure naturally.\n"
        "3. Zero outside knowledge: Use ONLY facts from the source text. Never invent context or entities.\n"
        "4. Format the body exclusively using safe HTML tags: <p>, <b>, <i>, <ul>, <li>, <blockquote>."
    )

    user_payload = (
        f"Original Title: {source_title}\n\n"
        f"Lead Paragraph: {lead_para}\n\n"
        f"Full Source Content:\n{full_content}"
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_payload,
        config=types.GenerateContentConfig(
            system_instruction=writer_instructions,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=8000,
            response_mime_type="application/json",
            response_schema=RewriteDraft,
        ),
    )

    if response.parsed:
        return response.parsed
    return RewriteDraft(**json.loads(response.text))


def pass_2_audit_draft(client, full_content: str, draft: RewriteDraft) -> AuditReport:
    """Stage 2: Adversarial auditor rigorously compares Source vs. Draft."""
    auditor_instructions = (
        "You are a strict, adversarial newsroom fact-checker and senior copy-editor. "
        "Your task is to compare the SOURCE text against the DRAFT rewrite.\n\n"
        "AUDIT CHECKLIST:\n"
        "1. ENTITY CHECK: Did the draft introduce proper names, titles, or designations not in the source "
        "(e.g., inferring a politician's name when the source only wrote 'Chief Minister', or adding 'private individuals')?\n"
        "2. NUMERIC & DATE CHECK: Are any numbers altered (e.g. changing '2000' to 'more than 2000'), dropped, or added?\n"
        "3. ATTRIBUTION & CONTEXT CHECK: Did the draft invent reporter Q&A context ('in response to questions'), "
        "emotional tone descriptions ('reacted emotionally'), or boilerplate claims not in the source?\n"
        "4. RESTRUCTURING: Did the draft simply copy sentence-by-sentence, or is it an original restructuring?\n\n"
        "Return is_faithful=true ONLY if zero ungrounded claims exist. Otherwise is_faithful=false."
    )

    audit_payload = (
        f"--- ORIGINAL SOURCE CONTENT ---\n{full_content}\n\n"
        f"--- DRAFT HEADLINES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- DRAFT CONTENT ---\n{draft.content}"
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=audit_payload,
        config=types.GenerateContentConfig(
            system_instruction=auditor_instructions,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=4000,
            response_mime_type="application/json",
            response_schema=AuditReport,
        ),
    )

    if response.parsed:
        return response.parsed
    return AuditReport(**json.loads(response.text))


def pass_3_polish_final(client, source_title: str, lead_para: str, full_content: str, draft: RewriteDraft, audit: AuditReport) -> RewriteDraft:
    """Stage 3: Rewrites the article and titles again, applying every audit critique."""
    editor_instructions = (
        "You are the Chief Editor of a prestigious Malayalam news organization. "
        "You have the ORIGINAL source article, an INITIAL draft, and an AUDITOR CRITIQUE.\n\n"
        "YOUR TASK:\n"
        "Produce the FINAL publication-ready article and 4 headlines by strictly resolving every critique from the auditor.\n\n"
        "MANDATORY INSTRUCTIONS:\n"
        "1. Remove every unsupported addition, inferred proper name, or hallucinated phrase flagged in the audit.\n"
        "2. Fix all numeric distortions: ensure numbers and statistical claims match the original source with 100% precision.\n"
        "3. Ensure the narrative is thoroughly restructured from scratch without copying the source's sentence-by-sentence order.\n"
        "4. Format the final content exclusively using HTML tags: <p>, <b>, <i>, <ul>, <li>, <blockquote>."
    )

    polish_payload = (
        f"--- ORIGINAL SOURCE TEXT ---\n{full_content}\n\n"
        f"--- INITIAL DRAFT TITLES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- INITIAL DRAFT BODY ---\n{draft.content}\n\n"
        f"--- AUDITOR EVALUATION & CRITIQUE ---\n"
        f"Is Faithful: {audit.is_faithful}\n"
        f"Unsupported Additions to Remove: {json.dumps(audit.unsupported_additions, ensure_ascii=False)}\n"
        f"Numeric Issues to Correct: {json.dumps(audit.numeric_issues, ensure_ascii=False)}\n"
        f"Editorial Directives: {audit.editorial_critique}\n\n"
        f"Rewrite the final version now, addressing all auditor points strictly."
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=polish_payload,
        config=types.GenerateContentConfig(
            system_instruction=editor_instructions,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=8000,
            response_mime_type="application/json",
            response_schema=RewriteDraft,
        ),
    )

    if response.parsed:
        return response.parsed
    return RewriteDraft(**json.loads(response.text))


# ==========================================
# 4. Orchestrator with Key Failover
# ==========================================

def execute_pipeline(source_title: str, lead_para: str, full_content: str, article_id: int) -> dict:
    """Runs Pass 1 (Write) -> Pass 2 (Audit) -> Pass 3 (Rewrite with Evaluation)."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=60.0)
            )

            # --- STAGE 1: DRAFT GENERATION ---
            logger.info(f"Article {article_id}: Running Stage 1 (Initial Draft) with {key_name}...")
            draft = pass_1_generate_draft(client, source_title, lead_para, full_content)

            # --- STAGE 2: ADVERSARIAL AUDIT ---
            logger.info(f"Article {article_id}: Running Stage 2 (Adversarial Audit)...")
            audit = pass_2_audit_draft(client, full_content, draft)

            # --- STAGE 3: REWRITE WITH EVALUATIONS ---
            if not audit.is_faithful or audit.unsupported_additions or audit.numeric_issues:
                logger.info(f"Article {article_id}: Audit flagged issues ({audit.unsupported_additions}). Running Stage 3 (Polish)...")
                final_draft = pass_3_polish_final(client, source_title, lead_para, full_content, draft, audit)
            else:
                logger.info(f"Article {article_id}: Audit passed completely clean. Proceeding to finalize.")
                final_draft = draft

            cleaned_result = verify_and_clean_output(final_draft)
            cleaned_result["key_used"] = key_name

            logger.info(f"✅ Successfully completed 3-stage rewrite for article {article_id} using {key_name}")
            return cleaned_result

        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            logger.warning(f"Pipeline failed on {key_name} for article {article_id}: {e}")

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
# 5. FastAPI Endpoint
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
        lead_paragraph = extract_first_paragraph(raw_content)

        result = execute_pipeline(
            source_title=raw_title,
            lead_para=lead_paragraph,
            full_content=raw_content,
            article_id=article_id,
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