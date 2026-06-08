from celery import Celery
from celery.schedules import crontab



celery = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

celery.conf.timezone = "Asia/Kolkata"

celery.conf.beat_schedule = {
    "fetch-rss-every-15-minutes": {
        "task": "rss_fetch.fetch_all_feeds",
        "schedule": 900.0,
    },

    "cleanup-old-data-daily": {
        "task": "cleanup_tasks.cleanup_old_data",
        "schedule": crontab(hour=3, minute=0) # every day at 3:00 AM IST
    },

    "trigger-client-wp-crons-every-15-minutes": {
        "task": "cron_trigger.trigger_client_wp_crons",
        "schedule": crontab(minute="*/15"),
    },
}

# IMPORT TASK MODULES LAST
import rss_fetch
import cron_trigger
import cleanup_tasks