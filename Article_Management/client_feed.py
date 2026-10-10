from fastapi import APIRouter

from database import SessionLocal

from models import (
    Client,
    DeliveryLog,
    Article
)

from datetime import (
    datetime,
    timedelta
)

from zoneinfo import ZoneInfo

import json


router = APIRouter()


IST = ZoneInfo("Asia/Kolkata")


# =========================================================
# Helper Functions
# =========================================================

def normalize_domain(domain: str) -> str:

    return (
        domain
        .lower()
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .strip("/")
    )


def get_category_limits(client):

    """
    Read category limits from the client's JSON field.

    Example:

    {
        "Entertainment": 8,
        "Kerala": 10,
        "India": 10
    }

    If a category is not present,
    it has no category-specific limit.
    """

    try:

        limits = json.loads(
            client.category_limits or "{}"
        )

        if not isinstance(limits, dict):

            return {}

        cleaned_limits = {}

        for category, limit in limits.items():

            try:

                limit = int(limit)

                if limit > 0:

                    cleaned_limits[
                        str(category).strip()
                    ] = limit

            except (
                ValueError,
                TypeError
            ):

                continue

        return cleaned_limits

    except (
        json.JSONDecodeError,
        TypeError
    ):

        return {}


def article_to_dict(
    article,
    now
):

    return {

        "id":
            article.id,

        "title":
            article.title,

        "content":
            article.content,

        "link":
            article.link,

        "image_url":
            article.image_url,

        "category":
            article.category,

        "published_at":
            article.published_at,

        "scheduled_publish_time":
            now.isoformat(),

        "is_breaking":
            bool(article.is_breaking)

    }


# =========================================================
# CLIENT FEED
# =========================================================

@router.get("/feed")
def client_feed(
    api_key: str,
    domain: str
):

    db = SessionLocal()

    try:

        # =================================================
        # Find Client
        # =================================================

        client = (
            db.query(Client)
            .filter_by(
                api_key=api_key,
                active=True
            )
            .first()
        )


        if not client:

            return {
                "error": "Invalid API Key"
            }


        # =================================================
        # Validate Domain
        # =================================================

        normalized_domain = (
            normalize_domain(domain)
        )

        allowed_domain = (
            normalize_domain(
                client.allowed_domain
            )
        )


        if normalized_domain != allowed_domain:

            return {
                "error": "Unauthorized domain"
            }


        # =================================================
        # Current Time
        # =================================================

        now = datetime.now(IST)


        # =================================================
        # Feed Cooldown
        # =================================================

        cooldown = timedelta(
            minutes=5
        )

        cooldown_now = datetime.now()


        if client.last_feed_request:

            elapsed = (
                cooldown_now
                - client.last_feed_request
            )


            if elapsed < cooldown:

                remaining = (
                    cooldown
                    - elapsed
                )


                return {

                    "error":
                        "Feed requested too frequently. "
                        f"Retry after {remaining.seconds} seconds."

                }


        client.last_feed_request = cooldown_now

        db.commit()


        # =================================================
        # Start Of Today
        # =================================================

        today_start = now.replace(

            hour=0,
            minute=0,
            second=0,
            microsecond=0

        )


        # =================================================
        # Allowed Categories
        # =================================================

        allowed_categories = [

            category.strip()

            for category
            in (
                client.subscribed_categories
                or ""
            ).split(",")

            if category.strip()

        ]


        if not allowed_categories:

            return []


        # =================================================
        # Category Limits
        # =================================================

        category_limits = (
            get_category_limits(client)
        )


        # =================================================
        # Determine Client Plan
        # =================================================

        if client.daily_post_limit == 25:

            tier_filter = (
                Article.show_25 == True
            )

        elif client.daily_post_limit == 50:

            tier_filter = (
                Article.show_50 == True
            )

        elif client.daily_post_limit == 100:

            tier_filter = (
                Article.show_100 == True
            )

        else:

            return {
                "error": "Invalid client plan"
            }


        # =================================================
        # Already Delivered Articles
        # =================================================

        delivered_subquery = (

            db.query(
                DeliveryLog.article_id
            )

            .filter(
                DeliveryLog.client_id
                == client.id
            )

            .subquery()

        )


        # =================================================
        # BREAKING NEWS
        #
        # Breaking news:
        #
        # - bypasses category limits
        # - bypasses normal daily quota
        # - must be subscribed category
        # - must not already be delivered
        # =================================================

        breaking_articles = (

            db.query(Article)

            .filter(

                Article.status
                == "approved",

                Article.is_breaking
                == True,

                Article.category.in_(
                    allowed_categories
                ),

                Article.created_at
                >= today_start,

                ~Article.id.in_(
                    delivered_subquery
                )

            )

            .order_by(
                Article.created_at.asc()
            )

            .all()

        )


        # =================================================
        # NORMAL ARTICLES ALREADY DELIVERED TODAY
        #
        # IMPORTANT:
        #
        # Breaking articles are NOT counted here.
        #
        # This means:
        #
        # 25 normal posts
        # +
        # any number of breaking posts
        #
        # =================================================

        normal_delivered_today = (

            db.query(DeliveryLog)

            .join(

                Article,

                Article.id
                == DeliveryLog.article_id

            )

            .filter(

                DeliveryLog.client_id
                == client.id,

                DeliveryLog.delivered_at
                >= today_start,

                Article.is_breaking
                == False

            )

            .count()

        )


        # =================================================
        # Remaining Normal Package
        # =================================================

        remaining_quota = (

            client.daily_post_limit
            - normal_delivered_today

        )


        if remaining_quota < 0:

            remaining_quota = 0


        # =================================================
        # NORMAL ARTICLE SELECTION
        # =================================================

        normal_articles = []


        if remaining_quota > 0:


            # ---------------------------------------------
            # Process each subscribed category separately
            # ---------------------------------------------

            for category in allowed_categories:


                # -----------------------------------------
                # Stop if overall package is full
                # -----------------------------------------

                if (
                    len(normal_articles)
                    >= remaining_quota
                ):

                    break


                # -----------------------------------------
                # Count how many NORMAL articles from this
                # category have already been delivered today
                # -----------------------------------------

                category_delivered_today = (

                    db.query(DeliveryLog)

                    .join(

                        Article,

                        Article.id
                        == DeliveryLog.article_id

                    )

                    .filter(

                        DeliveryLog.client_id
                        == client.id,

                        DeliveryLog.delivered_at
                        >= today_start,

                        Article.category
                        == category,

                        Article.is_breaking
                        == False

                    )

                    .count()

                )


                # -----------------------------------------
                # Check Category Limit
                # -----------------------------------------

                category_limit = (
                    category_limits.get(
                        category
                    )
                )


                # -----------------------------------------
                # If a category has a limit
                # -----------------------------------------

                if category_limit is not None:


                    category_remaining = (

                        category_limit
                        - category_delivered_today

                    )


                    # Category already reached limit

                    if category_remaining <= 0:

                        continue


                # -----------------------------------------
                # No category-specific limit
                # -----------------------------------------

                else:

                    category_remaining = (
                        remaining_quota
                    )


                # -----------------------------------------
                # Don't exceed overall client quota
                # -----------------------------------------

                slots_remaining = (

                    remaining_quota
                    - len(normal_articles)

                )


                slots = min(

                    category_remaining,

                    slots_remaining

                )


                if slots <= 0:

                    continue


                # -----------------------------------------
                # Fetch articles for this category
                # -----------------------------------------

                category_articles = (

                    db.query(Article)

                    .filter(

                        Article.status
                        == "approved",

                        tier_filter,

                        Article.category
                        == category,

                        Article.created_at
                        >= client.activated_at,

                        Article.is_breaking
                        == False,

                        ~Article.id.in_(
                            delivered_subquery
                        )

                    )

                    .order_by(

                        Article.created_at.asc()

                    )

                    .limit(slots)

                    .all()

                )


                normal_articles.extend(
                    category_articles
                )


        # =================================================
        # FINAL ARTICLE LIST
        # =================================================
        #
        # Breaking articles come first.
        #
        # Normal articles follow.
        #
        # =================================================

        articles = (

            breaking_articles
            + normal_articles

        )


        # =================================================
        # Convert To API Response
        # =================================================

        response_data = [

            article_to_dict(
                article,
                now
            )

            for article in articles

        ]


        return response_data


    finally:

        db.close()