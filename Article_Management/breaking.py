from fastapi import APIRouter, Depends, HTTPException
from database import SessionLocal
from Authentication.admin_auth import verify_admin
from models import Article

router = APIRouter()


@router.post("/breaking/{article_id}")
def mark_breaking(article_id: int, admin=Depends(verify_admin)):

    db = SessionLocal()

    article = db.query(Article).filter(
        Article.id == article_id
    ).first()

    if not article:
        db.close()
        raise HTTPException(
            status_code=404,
            detail="Article not found"
        )

    article.status = "approved"
    article.is_breaking = True

    db.commit()
    db.close()

    return {"message": "Marked as breaking"}
