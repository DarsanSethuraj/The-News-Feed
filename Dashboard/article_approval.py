from fastapi import (
    APIRouter,
    Depends,
    Request,
    HTTPException
)

from database import SessionLocal
from models import Article

from Authentication.admin_auth import verify_admin

from datetime import datetime, timedelta

from fastapi.templating import Jinja2Templates

from pydantic import BaseModel


templates = Jinja2Templates(
    directory="Templates"
)


router = APIRouter()


# ---------------------------------------------------------
# Article update model
# ---------------------------------------------------------

class ArticleUpdate(BaseModel):

    title: str
    content: str
    category: str
    image_url: str


# ---------------------------------------------------------
# Allowed categories
# ---------------------------------------------------------

ALLOWED_CATEGORIES = (
    "World",
    "India",
    "Kerala",
    "Entertainment",
    "Gulf",
    "Tech",
    "Sports",
    "Crime",
    "Uncategorized"
)


# ---------------------------------------------------------
# Pending articles
# ---------------------------------------------------------

@router.get("/admin/pending")
def admin_pending(
    request: Request,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        four_hour_ago = (
            datetime.utcnow()
            - timedelta(hours=4)
        )


        articles = (
            db.query(Article)
            .filter(
                Article.status == "pending",
                Article.category != "Uncategorized",
                Article.published_at >= four_hour_ago
            )
            .order_by(
                Article.published_at.desc()
            )
            .all()
        )


        now = datetime.utcnow()


        for article in articles:

            if article.published_at:

                age = (
                    now
                    - article.published_at
                )

                article.age_minutes = int(
                    age.total_seconds() / 60
                )

            else:

                article.age_minutes = 0


        article_count = len(articles)


        return templates.TemplateResponse(
            request=request,
            name="pending_articles.html",
            context={
                "request": request,
                "articles": articles,
                "article_count": article_count,
                "categories": ALLOWED_CATEGORIES
            }
        )

    finally:

        db.close()


# ---------------------------------------------------------
# Update article
#
# Updates:
# - title
# - content
# - category
# - image URL
# ---------------------------------------------------------

@router.post("/admin/update/{article_id}")
def update_article(
    article_id: int,
    article_data: ArticleUpdate,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        article = (
            db.query(Article)
            .filter(
                Article.id == article_id
            )
            .first()
        )


        if not article:

            raise HTTPException(
                status_code=404,
                detail="Article not found"
            )


        # -------------------------------------------------
        # Validate title
        # -------------------------------------------------

        title = article_data.title.strip()


        if not title:

            raise HTTPException(
                status_code=400,
                detail="Title cannot be empty"
            )


        # -------------------------------------------------
        # Validate content
        # -------------------------------------------------

        content = article_data.content


        if not content.strip():

            raise HTTPException(
                status_code=400,
                detail="Content cannot be empty"
            )


        # -------------------------------------------------
        # Validate category
        # -------------------------------------------------

        category = article_data.category.strip()


        if category not in ALLOWED_CATEGORIES:

            raise HTTPException(
                status_code=400,
                detail="Invalid category"
            )


        # -------------------------------------------------
        # Image URL
        # -------------------------------------------------

        image_url = article_data.image_url.strip()


        # -------------------------------------------------
        # Update database
        # -------------------------------------------------

        article.title = title

        article.content = content

        article.category = category

        article.image_url = image_url


        db.commit()

        db.refresh(article)


        return {
            "success": True,
            "message": "Article updated successfully",

            "article": {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "category": article.category,
                "image_url": article.image_url
            }
        }


    except HTTPException:

        db.rollback()

        raise


    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


    finally:

        db.close()