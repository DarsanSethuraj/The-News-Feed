from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from Authentication.admin_auth import verify_admin
from models import Article, CreateArticleRequest
from database import SessionLocal
from datetime import datetime

router = APIRouter()

templates = Jinja2Templates(
    directory="Templates"
)

@router.get("/admin/create-article-page")
def create_article_page(
    request: Request,
    admin=Depends(verify_admin)
):

    return templates.TemplateResponse(
        request=request,
        name="create_article.html",
        context={
            "request": request
        }
    )


@router.post("/admin/create-article")
def create_article(
    data: CreateArticleRequest,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        article = Article(
            title=data.title,
            content=data.content,
            category=data.category,
            image_url=data.image_url,
            author="Admin",
            status="pending",
            link=f"https://thenewsfeeds.in/{data.slug.strip()}",
            published_at=datetime.utcnow()
        )

        db.add(article)
        db.commit()
        db.refresh(article)

        return {
            "success": True,
            "article_id": article.id
        }

    finally:
        db.close()
        