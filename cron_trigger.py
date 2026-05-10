import requests
from celery_app import celery
from database import SessionLocal
from models import Client


@celery.task
def trigger_client_wp_crons():
    db = SessionLocal()

    try:
        clients = db.query(Client).all()

        for client in clients:
            site_url = client.allowed_domain.rstrip("/")

            try:
                response = requests.get(
                    f"{site_url}/wp-cron.php?doing_wp_cron",
                    timeout=15
                )

                print(
                    f"[WP-CRON] Triggered {site_url} "
                    f"Status: {response.status_code}"
                )

            except Exception as e:
                print(
                    f"[WP-CRON] Failed for {site_url}: {e}"
                )

    finally:
        db.close()