from fastapi import APIRouter
from database import SessionLocal
from models import Client, DeliveryLog, Article
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

router = APIRouter()

IST = ZoneInfo("Asia/Kolkata")

@router.get("/feed")
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

    
    cooldown = timedelta(minutes=5) # minimum time between feed requests

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

    if client.daily_post_limit == 25:
        tier_filter = Article.show_25 == True

    elif client.daily_post_limit == 50:
        tier_filter = Article.show_50 == True

    elif client.daily_post_limit == 100:
        tier_filter = Article.show_100 == True

    else:
        db.close()
        return {"error": "Invalid client plan"}

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


    normal_articles = (
        db.query(Article)
        .filter(
            Article.status == "approved",
            tier_filter,
            Article.category.in_(allowed_categories),
            Article.created_at >= client.activated_at,
            Article.is_breaking == False,
            ~Article.id.in_(delivered_subquery)
        )
        .order_by(Article.created_at.asc())
        .limit(remaining_quota)
        .all()
    )

    articles = breaking_articles + normal_articles

    response_data = []

    for article in articles:

        response_data.append({
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "link": article.link,
            "image_url": article.image_url,
            "category": article.category,
            "published_at": article.published_at,
            "scheduled_publish_time": now.isoformat(),
        })

    db.close()

    return response_data
   