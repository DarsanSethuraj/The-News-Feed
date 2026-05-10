from celery_app import celery
from database import SessionLocal
from models import Article, DeliveryLog
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@celery.task
def cleanup_old_data():

    db = SessionLocal()

    try:

        article_cutoff = (
            datetime.now(IST) - timedelta(hours=24)
        )

        log_cutoff = (
            datetime.now(IST) - timedelta(hours=48)
        )

        db.query(Article).filter(
            Article.created_at < article_cutoff
        ).delete(synchronize_session=False)

        db.query(DeliveryLog).filter(
            DeliveryLog.delivered_at < log_cutoff
        ).delete(synchronize_session=False)

        db.commit()

        print("Old data cleaned successfully")

    except Exception as e:

        db.rollback()

        print(f"Cleanup task failed: {e}")

    finally:

        db.close()