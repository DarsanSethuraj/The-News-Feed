from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse

from database import SessionLocal
from models import Article
from Authentication.admin_auth import verify_admin

router = APIRouter()


@router.post("/admin/update/{article_id}")
def update_article(
    article_id: int,
    content: str = Form(...),
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    article = db.query(Article).filter_by(id=article_id).first()

    if not article:
        db.close()
        return {"error": "Article not found"}

    article.content = content

    db.commit()

    db.close()

    return RedirectResponse(
        url="/admin/pending",
        status_code=303
    )