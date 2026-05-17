from fastapi import APIRouter, Depends
from database import SessionLocal
from Authentication.admin_auth import verify_admin
from models import Article


router = APIRouter()


@router.post("/approve/{article_id}")
def approve_article(article_id: int, admin=Depends(verify_admin)):
    
    db = SessionLocal()

    article = db.query(Article).filter_by(id=article_id).first()

    if not article:
        db.close()
        return {"error": "Article not found"}

    article.status = "approved"

    db.commit()
    db.close()

    return {"message": "Article approved"}