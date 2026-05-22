from fastapi import APIRouter, Depends, Request
from database import SessionLocal
from models import Article
from Authentication.admin_auth import verify_admin
from datetime import datetime, timedelta
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="Templates")


router = APIRouter()


@router.get("/admin/pending")
def admin_pending(
    request: Request,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        four_hours_ago = (
            datetime.utcnow() - timedelta(hours=4)
        )

        articles = db.query(Article).filter(
            Article.status == "pending",
            Article.category != "Uncategorized",
            Article.published_at >= four_hours_ago
        ).all()

        print(f"ARTICLE COUNT: {len(articles)}")

        return {
            "count": len(articles),
            "titles": [
                article.title
                for article in articles[:5]
            ]
        }

    finally:
        db.close()
        