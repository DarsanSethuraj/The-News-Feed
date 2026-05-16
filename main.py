import math

from fastapi import FastAPI, HTTPException
from database import engine
from models import Base
from database import SessionLocal
from models import Article, Client, DeliveryLog
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends
import secrets


security = HTTPBasic()

import os

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


IST = ZoneInfo("Asia/Kolkata")


def verify_admin(
    credentials: HTTPBasicCredentials = Depends(security)
):

    correct_username = secrets.compare_digest(
        credentials.username,
        ADMIN_USERNAME
    )

    correct_password = secrets.compare_digest(
        credentials.password,
        ADMIN_PASSWORD
    )

    if not (
        correct_username and correct_password
    ):

        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Backend Running"}


@app.get("/articles")
def get_articles():
    db = SessionLocal()
    articles = db.query(Article).all()
    db.close()

    return articles

@app.get("/pending-articles")
def get_pending_articles():
    db = SessionLocal()

    articles = db.query(Article).filter_by(status="pending").all()

    db.close()

    return articles

@app.post("/approve/{article_id}")
def approve_article(article_id: int, admin=Depends(verify_admin)):
    db = SessionLocal()

    article = db.query(Article).filter_by(id=article_id).first()

    if not article:
        db.close()
        return {"error": "Article not found"}

    article.status = "approved"

    db.commit()
    db.close()

    return {"message": "Article approved"}

@app.post("/reject/{article_id}")
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

@app.post("/breaking/{article_id}")
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


@app.get("/feed")
def client_feed(api_key: str, domain: str):
    db = SessionLocal()

    client = db.query(Client).filter_by(api_key=api_key, active=True).first()

    if not client:
        db.close()
        return {"error": "Invalid API Key"}
    
    normalized_domain = domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").strip("/")
    allowed_domain = client.allowed_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").strip("/")

    if normalized_domain != allowed_domain:
        db.close()
        return {"error": "Unauthorized domain"}
    
    now = datetime.now(IST)
    # Cooldown / Rate Limiting for API requests

    
    cooldown = timedelta(minutes=15)
    cooldown_now = datetime.now()

    if client.last_feed_request:

        elapsed = cooldown_now - client.last_feed_request

        if elapsed < cooldown:
            remaining = cooldown - elapsed

            return {
                "error": f"Feed requested too frequently. Retry after {remaining.seconds} seconds."
            }

    client.last_feed_request = cooldown_now
    db.commit()
    
    # Calculate remaining quota for the day

    today_start = now.replace(
    hour=0, minute=0, second=0, microsecond=0
    )

    delivered_today_count = db.query(DeliveryLog).filter(
        DeliveryLog.client_id == client.id,
        DeliveryLog.delivered_at >= today_start
    ).count()

    remaining_quota = client.daily_post_limit - delivered_today_count

    allowed_categories = [
        cat.strip()
        for cat in client.subscribed_categories.split(",")
        if cat.strip()
    ]

    delivered_subquery = (
        db.query(DeliveryLog.article_id)
        .filter(DeliveryLog.client_id == client.id)
        .subquery()
    )

    # Breaking news (bypasses quota)

    breaking_articles = (
        db.query(Article)
        .filter(
            Article.status == "approved",

            Article.is_breaking == True,

            Article.category.in_(allowed_categories),

            Article.created_at >= today_start,

            ~Article.id.in_(delivered_subquery)
        )
        .all()
    )

    if remaining_quota <= 0:

        response_data = [
            {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "link": article.link,
                "image_url": article.image_url,
                "category": article.category,
                "published_at": article.published_at,
                "scheduled_publish_time": now.isoformat(),
            }
            for article in breaking_articles
        ]

        db.commit()
        db.close()

        return response_data


    current_hour = now.hour

    # No posting between 12 AM and 6 AM
    
    if 0 <= current_hour < 6:
        if not breaking_articles:

            db.commit()
            db.close()

            return []

        response_data = [
            {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "link": article.link,
                "image_url": article.image_url,
                "category": article.category,
                "published_at": article.published_at,
                "scheduled_publish_time": now.isoformat(),
            }
            for article in breaking_articles
        ]

        db.commit()
        db.close()

        return response_data

    

    # Calculate remaining active hours
    # Active posting window ends at 12 AM
    # Posting allowed only from 6 AM to 12 AM

    hours_remaining = max(
        1,
        24 - current_hour
    )

    # Remove non-posting hours (12 AM - 6 AM)
    if current_hour < 24:

        inactive_hours_remaining = 6

        hours_remaining -= inactive_hours_remaining

    hours_remaining = max(1, hours_remaining)

    posts_per_hour = remaining_quota / hours_remaining

    # Prime time boost
    if 18 <= current_hour < 22:

        posts_per_hour *= 1.8

    articles_to_release = max(
        1 if remaining_quota > 0 else 0,
        math.ceil(posts_per_hour)
    )

    if articles_to_release <= 0:

        db.commit()
        db.close()

        return []

    normal_articles = (
        db.query(Article)
        .filter(
            Article.status == "approved",

            Article.category.in_(allowed_categories),

            Article.created_at >= client.activated_at,

            Article.created_at >= today_start,

            ~Article.id.in_(delivered_subquery)
        )
        .order_by(Article.created_at.desc())
        .limit(articles_to_release)
        .all()
    )

    articles = breaking_articles + normal_articles

    publish_times = []

    base_time = now

    spacing_minutes = max(
        10,
        int((hours_remaining * 60) / max(1, articles_to_release))
    )

    for i in range(len(articles)):

        publish_time = base_time + timedelta(
            minutes=i * spacing_minutes
        )

        # No publishing between 12 AM and 6 AM
        if 0 <= publish_time.hour < 6:

            publish_time = publish_time.replace(
                hour=6,
                minute=0,
                second=0,
                microsecond=0
            )

        publish_times.append(publish_time)

    response_data = []

    for article, publish_time in zip(articles, publish_times):

        response_data.append({
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "link": article.link,
            "image_url": article.image_url,
            "category": article.category,
            "published_at": article.published_at,
            "scheduled_publish_time": publish_time.isoformat(),
        })

    db.close()

    return response_data
    


from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="Templates")


@app.get("/admin/pending")
def admin_pending(
    request: Request,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    four_hours_ago = (
        datetime.utcnow() - timedelta(hours=4)
    )

    articles = db.query(Article).filter(
        Article.status == "pending",
        Article.category != "Uncategorized",
        Article.created_at >= four_hours_ago
    ).all()

    db.close()

    return templates.TemplateResponse(
        request=request,
        name="pending_articles.html",
        context={
            "request": request,
            "articles": articles
        }
    )

@app.get("/categories")
def get_categories():
    return [
        "World",
        "India",
        "Kerala",
        "Entertainment",
        "Gulf",
        "Tech",
        "Sports",
        "Crime",        
    ]


from pydantic import BaseModel
from typing import List


class DeliveryAckRequest(BaseModel):
    api_key: str
    article_ids: List[int]


@app.post("/ack-delivery")
def acknowledge_delivery(payload: DeliveryAckRequest):
    db = SessionLocal()

    try:
        client = (
            db.query(Client)
            .filter(Client.api_key == payload.api_key)
            .first()
        )

        if not client:
            raise HTTPException(status_code=401, detail="Invalid API key")

        now = datetime.now(IST)

        for article_id in payload.article_ids:

            already_exists = (
                db.query(DeliveryLog)
                .filter(
                    DeliveryLog.client_id == client.id,
                    DeliveryLog.article_id == article_id
                )
                .first()
            )

            if already_exists:
                continue

            db.add(
                DeliveryLog(
                    client_id=client.id,
                    article_id=article_id,
                    delivered_at=now
                )
            )

        db.commit()

        return {
            "success": True,
            "acknowledged": payload.article_ids
        }

    finally:
        db.close()

@app.get("/admin/clients")
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


