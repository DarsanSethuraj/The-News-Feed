from fastapi import APIRouter, Request, Depends
from database import SessionLocal
from models import Client, DeliveryLog, Article
from Authentication.admin_auth import verify_admin
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi.templating import Jinja2Templates

IST = ZoneInfo("Asia/Kolkata")

templates = Jinja2Templates(directory="Templates")

router = APIRouter()

@router.get("/admin/clients")
def client_dashboard(
    request: Request,
    username: str = Depends(verify_admin)
):
    
    db = SessionLocal()

    today_start = datetime.now(IST).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    clients = db.query(Client).all()

    dashboard_data = []

    for client in clients:

        today_count = db.query(DeliveryLog).filter(
            DeliveryLog.client_id == client.id,
            DeliveryLog.delivered_at >= today_start
        ).count()

        latest_delivery = (
            db.query(DeliveryLog, Article)
            .join(
                Article,
                DeliveryLog.article_id == Article.id
            )
            .filter(
                DeliveryLog.client_id == client.id
            )
            .order_by(DeliveryLog.delivered_at.desc())
            .first()
        )

        latest_article_title = None
        latest_delivery_time = None

        if latest_delivery:
            log, article = latest_delivery
            latest_article_title = article.title
            latest_delivery_time = log.delivered_at

        dashboard_data.append({
            "client": client,
            "today_count": today_count,
            "remaining": (
                client.daily_post_limit - today_count
            ),
            "latest_article_title": latest_article_title,
            "latest_delivery_time": latest_delivery_time
        })

    return templates.TemplateResponse(
        request=request,
        name="client_dashboard.html",
        context={
            "request": request,
            "dashboard_data": dashboard_data
        }
    )
