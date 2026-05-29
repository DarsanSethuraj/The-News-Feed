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

    one_hour_ago = (
        datetime.utcnow() + timedelta(hours=1)
    )

    articles = db.query(Article).filter(
        Article.status == "pending",
        Article.category != "Uncategorized",
        Article.published_at >= one_hour_ago
    ).all()

    article_count = len(articles)

    response = templates.TemplateResponse(
        request=request,
        name="pending_articles.html",
        context={
            "request": request,
            "articles": articles,
            "article_count": article_count
        }
    )

    db.close()

    return response