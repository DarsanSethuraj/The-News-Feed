from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates

from Authentication.admin_auth import verify_admin

from models import Article, CreateArticleRequest
from database import SessionLocal

from datetime import datetime


router = APIRouter()


templates = Jinja2Templates(
    directory="Templates"
)


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
# Create Article Page
# ---------------------------------------------------------

@router.get("/admin/create-article-page")
def create_article_page(
    request: Request,
    admin=Depends(verify_admin)
):

    return templates.TemplateResponse(
        request=request,
        name="create_article.html",
        context={
            "request": request,
            "categories": ALLOWED_CATEGORIES
        }
    )


# ---------------------------------------------------------
# Create Article
# ---------------------------------------------------------

@router.post("/admin/create-article")
def create_article(
    data: CreateArticleRequest,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        # -------------------------------------------------
        # Validate title
        # -------------------------------------------------

        title = data.title.strip()

        if not title:

            raise HTTPException(
                status_code=400,
                detail="Title cannot be empty"
            )


        # -------------------------------------------------
        # Validate content
        # -------------------------------------------------

        content = data.content

        if not content.strip():

            raise HTTPException(
                status_code=400,
                detail="Content cannot be empty"
            )


        # -------------------------------------------------
        # Validate category
        # -------------------------------------------------

        category = data.category.strip()

        if category not in ALLOWED_CATEGORIES:

            raise HTTPException(
                status_code=400,
                detail="Invalid category"
            )


        # -------------------------------------------------
        # Validate slug
        # -------------------------------------------------

        slug = data.slug.strip()

        if not slug:

            raise HTTPException(
                status_code=400,
                detail="Slug cannot be empty"
            )


        # -------------------------------------------------
        # Image URL
        # -------------------------------------------------

        image_url = (
            data.image_url.strip()
            if data.image_url
            else None
        )


        # -------------------------------------------------
        # Create article
        # -------------------------------------------------

        article = Article(

            title=title,

            content=content,

            category=category,

            image_url=image_url,

            author="Admin",

            status="pending",

            link=f"https://thenewsfeeds.in/{slug}",

            published_at=datetime.utcnow()

        )


        # -------------------------------------------------
        # Save
        # -------------------------------------------------

        db.add(article)

        db.commit()

        db.refresh(article)


        # -------------------------------------------------
        # Response
        # -------------------------------------------------

        return {
            "success": True,
            "article_id": article.id
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