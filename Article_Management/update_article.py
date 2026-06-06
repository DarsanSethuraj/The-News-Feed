from fastapi import APIRouter, Depends
from database import SessionLocal
from models import Article, ArticleUpdate
from Authentication.admin_auth import verify_admin

router = APIRouter()


@router.post("/admin/update/{article_id}")
def update_article(
    article_id: int,
    data: ArticleUpdate,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    article = db.query(Article).filter_by(id=article_id).first()

    if not article:
        db.close()
        return {"error": "Article not found"}

    article.content = data.content

    db.commit()
    db.close()

    return {"success": True}