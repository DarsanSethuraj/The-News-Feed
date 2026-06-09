from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from Authentication.admin_auth import verify_admin

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