from celery import Celery
from celery.schedules import crontab

celery = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

celery.conf.beat_schedule = {
    "fetch-rss-every-10-seconds": {
        "task": "rss_fetch.fetch_all_feeds",
        "schedule": 30.0,
    },

    "cleanup-old-data-daily": {
        "task": "cleanup_tasks.cleanup_old_data",
        "schedule": 86400.0,  # 24 hours
    },

    "trigger-client-wp-crons-every-5-minutes": {
        "task": "cron_trigger.trigger_client_wp_crons",
        "schedule": crontab(minute="*/5"),
    },
}

# IMPORT TASK MODULES LAST
import rss_fetch
import cron_trigger
import cleanup_tasks