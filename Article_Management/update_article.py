import html
import re
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from database import SessionLocal
from pydantic import BaseModel
from models import Article
from Authentication.admin_auth import verify_admin

router = APIRouter()

ALLOWED_TAGS = {"p", "br", "b", "i", "strong", "em", "ul", "ol", "li", "blockquote"}


def sanitize_html(raw_html: str) -> str:
    """Sanitizes HTML content, stripping out disallowed tags and all tag attributes."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return "".join(str(c) for c in soup.contents).strip()


def sanitize_title(title: str) -> str:
    """Strips all HTML tags and collapses whitespace from titles."""
    clean = re.sub(r"<[^>]*>", "", title or "")
    return html.unescape(clean).strip()


class ArticleUpdate(BaseModel):
    title: str
    content: str


@router.post("/admin/update/{article_id}")
def update_article(
    article_id: int,
    payload: ArticleUpdate,
    admin=Depends(verify_admin)
):
    db = SessionLocal()

    try:
        article = db.query(Article).filter(Article.id == article_id).first()

        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Sanitize before saving to database
        clean_title = sanitize_title(payload.title)
        clean_content = sanitize_html(payload.content)

        if not clean_title:
            raise HTTPException(status_code=422, detail="Article title cannot be empty.")
        if not clean_content:
            raise HTTPException(status_code=422, detail="Article content cannot be empty.")

        article.title = clean_title
        article.content = clean_content

        db.commit()

        return {"success": True, "message": "Article updated successfully"}

    finally:
        db.close()