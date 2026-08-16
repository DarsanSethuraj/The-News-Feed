from fastapi import APIRouter, Depends
from Authentication.admin_auth import verify_admin
from database import SessionLocal
from models import Article


router = APIRouter()


@router.post("/reject/{article_id}")
def reject_article(article_id: int, admin=Depends(verify_admin)):
    
    db = SessionLocal()

    article = db.query(Article).filter_by(id=article_id).first()

    if not article:
        db.close()
        return {"error": "Article not found"}

    article.status = "rejected"

    db.commit()
    db.close()

    return {"message": "Article rejected"}
