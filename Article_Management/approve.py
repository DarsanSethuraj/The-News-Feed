from fastapi import APIRouter, Depends
from database import SessionLocal
from Authentication.admin_auth import verify_admin
from models import Article


router = APIRouter()


@router.post("/approve/{article_id}")
def approve_article(
    article_id: int,
    data: dict = Body(...),
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    article = db.query(Article).filter_by(
        id=article_id
    ).first()

    if not article:
        db.close()
        return {"error": "Article not found"}

    tiers = data.get("tiers", [])

    article.status = "approved"

    article.show_25 = 25 in tiers
    article.show_50 = 50 in tiers
    article.show_100 = 100 in tiers

    db.commit()
    db.close()

    return {
        "message": "Article approved"
    }