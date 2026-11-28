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


# ==========================================
# 1. Pydantic Schemas for Structured Output
# ==========================================

class RewriteResponse(BaseModel):
    titles: List[str] = Field(
        min_length=4,
        max_length=4,
        description=(
            "Exactly 4 distinct, full, informative Malayalam newsdesk headlines derived strictly "
            "from ONLY the first paragraph of the news and directly related to the source title."
        )
    )
    content: str = Field(
        description="Restructured and rewritten Malayalam news article in clean HTML paragraphs (<p>)."
    )


class AuditReport(BaseModel):
    has_faults: bool = Field(
        description="True ONLY if concrete numbers/names were dropped, Latin-script words were used, ungrounded details were added, or source titles were altered."
    )
    specific_faults: List[str] = Field(
        default_factory=list,
        description="Precise list of specific factual errors, dropped numbers, Latin-script words, or ungrounded details that must be patched."
    )


# ==========================================
# 2. Text and HTML Sanitization
# ==========================================

def clean_html_noise(raw_html: str) -> str:
    """Removes scripts, styles, and non-content noise while preserving article HTML tags (including <p>, <a>, etc.)."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav", "svg", "figure"]):
        tag.decompose()
    return str(soup).strip()


def sanitize_html(raw_html: str) -> str:
    """Sanitizes HTML content, stripping out disallowed tags and all attributes."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return "".join(str(c) for c in soup.contents).strip()


def verify_and_clean_output(data: RewriteResponse) -> dict:
    """Sanitizes headlines, normalizes Unicode, and cleans HTML body."""
    cleaned_titles = []
    seen = set()

    for t in data.titles:
        t_norm = unicodedata.normalize("NFC", t)
        clean_t = re.sub(r"<[^>]*>", "", t_norm).strip()
        clean_t = re.sub(r"^(?:[0-9]{1,2}[.)\]]\s*|[#*\-•]\s*)", "", clean_t).strip()

        if not clean_t or clean_t in seen:
            continue

        seen.add(clean_t)
        cleaned_titles.append(clean_t)

    while len(cleaned_titles) < 4:
        fallback = cleaned_titles[0] if cleaned_titles else "പ്രധാന വാർത്തകൾ"
        cleaned_titles.append(f"{fallback} - കൂടുതൽ വിവരങ്ങൾ")

    content_norm = unicodedata.normalize("NFC", data.content)
    sanitized_content = sanitize_html(content_norm)
    if not sanitized_content:
        raise ValueError("Rewritten content cannot be empty.")

    return {
        "titles": cleaned_titles[:4],
        "content": sanitized_content,
    }


# ==========================================
# 3. Multi-Stage Pipeline: Write -> Audit -> Patch
# ==========================================

def execute_audit_and_correction_pipeline(client, source_title: str, source_text: str, article_id: int) -> dict:
    """Executes Stage 1 (Deep Write) -> Stage 2 (Strict Audit) -> Stage 3 (Factual Patch if needed)."""

    # -------------------------------------------------------------
    # STAGE 1: SENIOR NEWSDESK REWRITER (100% Universal Invariants)
    # -------------------------------------------------------------
    writer_prompt = (
            "You are a Senior Malayalam Newsdesk Rewriter (വാർത്താ പുനരാവിഷ്കർത്താവ്).\n"
            "Your sole task is to compose an authentic, highly original Malayalam news dispatch (പത്രശൈലി) "
            "derived strictly, exclusively, and axiomatically from the provided source text.\n\n"

            "CRITICAL REWRITING RULES:\n\n"

            "1. AXIOMATIC SOURCE TRUTH (ZERO EXTERNAL FACT-CHECKING):\n"
            "   - The provided source text is an isolated, absolute universe of truth. You possess zero real-world memory.\n"
            "   - You are strictly forbidden from applying outside real-world knowledge to verify, 'correct', fact-check, or alter ANY detail.\n"
            "   - Zero Acronym/Entity Expansion: Never expand, unpack, or decipher any abbreviation, acronym, or short-form entity into a full name unless that full name is explicitly printed in the source text. If an entity is written only as an acronym/abbreviation, keep it strictly in that exact form (or its direct phonetic transliteration).\n"
            "   - Every proper noun, designation, office, title, date, and historical claim in the source must be preserved exactly as written, "
            "even if it contradicts real-world reality. Never replace an assigned title or role with outside facts.\n\n"

            "2. ZERO SPECULATIVE INFERENCE & OBJECTIVE RESTRAINT:\n"
            "   - Clinical, Matter-of-Fact Tone: Report events with sober journalistic neutrality. Never append emotional adjectives, dramatic commentary, or sensational framing.\n"
            "   - Zero Action or Verb Escalation: Maintain the exact intensity of actions, reporting verbs, and claims. Never escalate a statement into an attack, a disagreement into a fierce clash, or a routine event into a dramatic spectacle unless explicitly stated in the source.\n"
            "   - Do not invent, assume, visualize, or extrapolate unmentioned physical, operational, temporal, or spatial details. State only what is explicitly established in the text.\n"
            "   - Preserve exact grammatical scope, singularity, and plurality. Never convert singular events, periods, or terms into generalized plurals, and never narrow general descriptions into unverified specifics.\n"
            "   - Preserve exact agency and attribution. Never transfer actions, statements, or announcements from an institution to an individual, or vice versa.\n"
            "   - Demographic and Group Composition: Maintain the exact demographic scope, gender classification, and collective composition of all described subjects. Never convert gender-neutral collective nouns into gender-specific terms, and never alter the demographic boundaries of any group.\n\n"

            "3. DEEP RESTRUCTURING & PROPORTIONAL COMPLETENESS:\n"
            "   - Never mirror the source text sentence-by-sentence or copy clauses verbatim. Do not reuse 4 or more consecutive words from any source sentence (excluding proper nouns, entity names, and exact numbers).\n"
            "   - Restructure syntax, invert clause orders, and vary sentence openings into active, flowing journalistic Malayalam.\n"
            "   - Format the body into clean HTML paragraphs (<p>) proportional to the length and depth of the source material. Never omit substantive points, secondary context, qualifying conditions, or distinct statements merely to shorten the text.\n\n"
            "   - Never drop or generalize specific background anecdotes, defining historical milestones, or illustrative traits into vague generic descriptions; retain concrete details while freshly rephrasing their syntax.\n\n"

            "4. PROPER NOUN & ACTOR COMPLETENESS:\n"
            "   - Every named person, organization, and actor present in the source MUST be explicitly named in the output. Never omit a person's name or reduce them solely to their title.\n\n"

            "5. NUMERICAL & QUANTITATIVE FIDELITY (ARABIC DIGITS):\n"
            "   - Preserve every discrete numerical figure with 100% precision strictly in standard Arabic digits without exception.\n"
            "   - Exhaustive Numerical Retention: In any sequence, list, or statement containing multiple figures, every individual number must be explicitly retained. Never omit an intermediate value, baseline count, or qualifying quantity.\n"
            "   - Never convert digits into spelled-out Malayalam words under any circumstances.\n"
            "   - Never generalize, round off, or substitute exact figures with descriptive words.\n\n"
            
            "6. DATELINE PRESERVATION:\n"
            "   - If the source begins with a reporting location, preserve it strictly as an isolated bold prefix in Malayalam at the very start of the first paragraph (format: '<p><b>[Location]:</b> ...</p>'). Never absorb it into the sentence grammar.\n"
            "   - If the source does NOT begin with a reporting location, do NOT invent, assume, or add any dateline prefix.\n\n"

            "7. PURE MALAYALAM DICTION: Never use unquoted English words written in Latin script anywhere within the Malayalam text. Always express concepts using standard, authentic Malayalam journalistic vocabulary.\n\n"

            "HEADLINE REQUIREMENTS (MALAYALAM NEWSDESK STANDARD):\n"
            "- Provide exactly 4 genuinely distinct, well-crafted Malayalam headlines in 'titles'—do NOT produce 4 minor word-order tweaks of the exact same sentence.\n"
            "- STRICT SOURCE SCOPE (FIRST PARAGRAPH + SOURCE TITLE ONLY):\n"
            "  * Lead-Paragraph Exclusivity: Every fact, name, number, and detail used in all 4 headlines MUST come strictly and exclusively from the opening lead paragraph (first substantive paragraph) of the Source Content and the Source Title. NEVER pull facts, statements, or details from the second paragraph or later sections of the article.\n"
            "  * Source-Title Anchoring: Every headline MUST remain directly related to and aligned with the central topic, event, and focus of the 'Source Title'. Do not drift to a secondary or unrelated angle.\n"
            "- LENGTH & COMPLETENESS:\n"
            "  * Headlines do NOT need to be artificially short. Write full, clear, informative Malayalam newsdesk headlines that capture the complete meaning of the lead paragraph and source title without sacrificing key context.\n"
            "- FOUR DISTINCT STRUCTURAL ANGLES (ALL GROUNDED IN THE FIRST PARAGRAPH & SOURCE TITLE):\n"
            "  1. [Direct Lead Framing]: Clear, straightforward journalistic presentation of the main event from the opening paragraph in alignment with the source title.\n"
            "  2. [Actor / Subject-First Framing]: Leads with the key named person, group, or institution from the source title / first paragraph and highlights their specific action, decision, or statement.\n"
            "  3. [Reason / Outcome / Dual-Aspect Framing]: Highlights the cause, reason, result, or dual perspective contained within the first paragraph and source title.\n"
            "  4. [Desk Split / Inverted Syntax Framing]: Uses an alternative Malayalam desk structure (e.g., '[Topic/Actor]: [Detailed Lead Fact]' or inverted clause order) to present the same source-title focus freshly.\n"
            "- STYLE & FIDELITY RULES:\n"
            "  * Never copy 4 or more consecutive words from the source headline or first paragraph (excluding proper nouns, entity names, and exact numbers).\n"
            "  * Every headline MUST strictly obey Rules 1–7 (zero external facts, zero acronym expansion, zero verb escalation, Arabic digits only, and zero Latin-script words).\n"
            "  * Zero clickbait, teaser phrases ('ഞെട്ടിക്കുന്ന', 'ഇതാ കാരണം', etc.), exclamation marks, or HTML tags/numbering.\n\n"

            "FORMATTING REQUIREMENTS:\n"
            "- Return the article body in 'content' exclusively formatted using clean HTML tags: <p>, <b>, <i>, <ul>, <li>, <blockquote>.\n"
            "- Do not use markdown backticks (```), <h1>/<h2> tags, or tag attributes."
        )

    user_input_draft = (
        f"Source Title: {source_title}\n\n"
        f"Source Content (with HTML tags):\n{source_text}"
    )

    logger.info(f"Article {article_id}: Stage 1 - Generating deep rewrite...")
    resp_draft = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_input_draft,
        config=types.GenerateContentConfig(
            system_instruction=writer_prompt,
            temperature=0.3,
            max_output_tokens=6000,
            response_mime_type="application/json",
            response_schema=RewriteResponse,
        ),
    )
    draft: RewriteResponse = resp_draft.parsed if resp_draft.parsed else RewriteResponse(**json.loads(resp_draft.text))

    # -------------------------------------------------------------
    # STAGE 2: STRICT AUDIT & CRITIC (100% Universal Invariants)
    # -------------------------------------------------------------
    audit_prompt = (
        "You are an adversarial source-fidelity auditor and quality controller.\n"
        "Your sole task is to conduct a strict factual and linguistic audit of the REWRITTEN DRAFT against the ORIGINAL SOURCE.\n"
        "Treat the ORIGINAL SOURCE as the absolute definition of truth. Do NOT fact-check against the real world.\n\n"

        "INSPECT THE DRAFT FOR ONLY THESE CRITICAL DEFECTS:\n"
        "1. EXHAUSTIVE NUMERICAL RECONCILIATION: Did the draft omit ANY discrete numerical figure present in the source, including intermediate values within multi-number statements, or write ANY number in spelled-out words instead of Arabic digits? (Every individual number appearing in the source must have a corresponding figure in the draft).\n"
        "2. LATIN SCRIPT & UNTRANSLATED LOANWORDS: Did the draft include any English words written in Latin script rather than authentic Malayalam vocabulary?\n"
        "3. DROPPED ACTORS OR TITLES: Did the draft omit any named person, group, or official entity, or drop their assigned titles?\n"
        "4. OUTSIDE KNOWLEDGE INJECTION: Did the draft alter, replace, or 'correct' any title, role, or claim using external real-world knowledge?\n"
        "5. UNGROUNDED EXTRAPOLATION: Did the draft invent unmentioned physical, operational, temporal, or spatial details not explicitly stated in the source?\n"
        "6. SUBSTANTIVE FACTUAL OMISSIONS: Did the draft omit, skip, or summarize away ANY concrete event, statement, explanation, qualifying context, or substantive factual detail present in the source text?\n\n"
        "7. ORTHOGRAPHY, TYPOGRAPHY & WORD BOUNDARIES: Did the draft contain any spelling errors, malformed character ligatures, conflicting diacritics or vowel signs, missing consonant geminations, missing whitespace between adjacent words, or non-standard transliterations?\n\n"
        "8. DRAMATIC ESCALATION & HYPERBOLE: Did the draft add unstated emotional intensifiers, sensational adjectives, or escalate the intensity of statements, disagreements, or actions beyond the plain wording of the source?\n\n"
        "9. UNAUTHORIZED ACRONYM EXPANSION: Did the draft unpack, expand, or resolve ANY acronym, abbreviation, or short-form entity into a full name that does NOT appear verbatim in the source text? (If the source uses only an acronym, any expanded full name in the draft is an immediate defect).\n\n"
        "10. HEADLINE SCOPE & FIDELITY: Did ANY of the 4 draft headlines (a) include facts from the 2nd paragraph or later instead of strictly the first paragraph and source title, (b) drift away from the core topic of the ORIGINAL SOURCE TITLE, (c) near-duplicate another draft headline, or (d) violate Rules 1–9 (Latin script, spelled-out numbers, ungrounded claims, or sensational escalation)?\n\n"

        "DECISION CRITERIA (VERY IMPORTANT):\n"
        "- Set has_faults=true ONLY if one of the concrete defects above is present. List exact actionable instructions under specific_faults: 'Restore missing number: [value]', 'Replace Latin script text [word] with Malayalam', 'Restore entity [name]', 'Neutralize dramatic phrasing: [word]', 'Remove sensational modifier: [word]', 'Remove unauthorized acronym expansion: [expanded name] -> use [original acronym]' etc.\n"
        "- Do NOT flag fresh phrasing, active sentence structures, clause inversions, or paragraph consolidation as faults. Distinct syntax is desired and mandatory.\n"
        "- If all facts, numbers, names, and substantive details are preserved without outside injections or Latin-script words, set has_faults=false and leave specific_faults empty."
    )

    user_input_audit = (
        f"--- ORIGINAL SOURCE TITLE ---\n{source_title}\n\n"
        f"--- ORIGINAL SOURCE TEXT ---\n{source_text}\n\n"
        f"--- DRAFT HEADLINES ---\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
        f"--- DRAFT CONTENT ---\n{draft.content}"
    )

    logger.info(f"Article {article_id}: Stage 2 - Running deterministic audit...")
    resp_audit = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_input_audit,
        config=types.GenerateContentConfig(
            system_instruction=audit_prompt,
            temperature=0.0,
            max_output_tokens=2000,
            response_mime_type="application/json",
            response_schema=AuditReport,
        ),
    )
    audit: AuditReport = resp_audit.parsed if resp_audit.parsed else AuditReport(**json.loads(resp_audit.text))

    # -------------------------------------------------------------
    # STAGE 3: FACTUAL CORRECTION PATCH (100% Universal Invariants)
    # -------------------------------------------------------------
    if audit.has_faults and audit.specific_faults:
        logger.info(f"Article {article_id}: Stage 3 - Auditor flagged discrepancies ({audit.specific_faults}). Applying patch...")

        patch_prompt = (
            "You are a Senior Newsdesk Editor.\n"
            "Your task is to apply a surgical correction patch to the 'Initial Draft' to fix ONLY the specific issues flagged by the auditor.\n\n"

            "CRITICAL CORRECTION RULES (NO UNDO LOOP):\n"
            "1. PRESERVE THE REWRITTEN SYNTAX: The 'Initial Draft' is your primary narrative baseline. "
            "Do NOT revert sentences, vocabulary, or clause structures back to the original source text.\n"
            "2. SURGICAL REPAIR ONLY: Fix only the exact faults listed in 'Auditor Flags' (e.g. restore an omitted quantitative value in Arabic digits, replace Latin-script English text with authentic Malayalam vocabulary, restore an omitted entity name/title, correct corrupted character combinations/typos, or excise an ungrounded detail).\n"
            "3. NO LOSS OF REWRITTEN QUALITY: Keep the fresh, active journalistic Malayalam prose intact while making the text 100% factually compliant.\n"
            "4. HEADLINES: Ensure all 4 headlines are distinct, pure Malayalam, free of clickbait, directly related to the 'Original Source Title', and strictly grounded ONLY in the opening first paragraph of the source content (plus the source title). Do not truncate them artificially, and do not pull facts from paragraph 2 onward."        )

        user_input_patch = (
            f"Auditor Flags to Fix:\n"
            f"{chr(10).join('- ' + f for f in audit.specific_faults)}\n\n"
            f"Original Source Title:\n{source_title}\n\n"
            f"Draft Headlines for Reference:\n{json.dumps(draft.titles, ensure_ascii=False)}\n\n"
            f"Initial Draft (PRIMARY BASELINE TO PRESERVE AND PATCH):\n{draft.content}\n\n"
            f"Original Source Content (FOR FACT-CHECKING REFERENCE ONLY):\n{source_text}"
        )

        resp_patch = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_input_patch,
            config=types.GenerateContentConfig(
                system_instruction=patch_prompt,
                temperature=0.3,
                max_output_tokens=6000,
                response_mime_type="application/json",
                response_schema=RewriteResponse,
            ),
        )
        final_draft: RewriteResponse = resp_patch.parsed if resp_patch.parsed else RewriteResponse(**json.loads(resp_patch.text))
        logger.info(f"Article {article_id}: Stage 3 - Successfully applied surgical corrections.")
    else:
        logger.info(f"Article {article_id}: Stage 2 - Draft passed audit with zero defects. Finalizing.")
        final_draft = draft

    return verify_and_clean_output(final_draft)


# ==========================================
# 4. Failover Engine & API Runner
# ==========================================

def call_gemini_with_failover(source_title: str, source_text: str, article_id: int) -> dict:
    """Executes the pipeline with multi-key failover and timeout."""
    if not GEMINI_KEYS:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured.")

    last_error = None

    for key_name, api_key in GEMINI_KEYS:
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=60_000)
            )

            result = execute_audit_and_correction_pipeline(client, source_title, source_text, article_id)
            result["key_used"] = f"{key_name} ({GEMINI_MODEL})"
            logger.info(f"Successfully finished rewrite for article {article_id} using {key_name}")
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