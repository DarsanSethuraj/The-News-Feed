from celery_app import celery
import feedparser
import requests
from database import SessionLocal
from models import Article
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scraper import scrape_article


FEEDS = [
    "https://www.asianetnews.com/rss",
    "https://www.madhyamam.com/feeds.xml",
    "https://malayalam.news18.com/commonfeeds/v1/mal/rss/money.xml",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_published_at(entry) -> datetime:
    if entry.get("published"):
        try:
            return (
                parsedate_to_datetime(entry.published)
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
        except Exception:
            pass

    parsed_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_struct:
        return datetime(*parsed_struct[:6])

    return datetime.utcnow()


@celery.task
def fetch_all_feeds():
    db = SessionLocal()

    try:
        for url in FEEDS:
            try:
                res = requests.get(url, headers=HEADERS, timeout=15)
                res.raise_for_status()
                feed = feedparser.parse(res.content)
            except Exception as e:
                print(f"Feed fetch failed for {url}: {e}")
                continue

            if not feed.entries:
                print(f"No entries parsed for {url} (bozo={feed.bozo})")
                continue

            for entry in feed.entries[:10]:
                link = getattr(entry, "link", None)
                if not link or "/videos/" in link or "/gallery/" in link:
                    continue

                existing = db.query(Article).filter_by(link=link).first()
                if existing:
                    continue

                try:
                    scraped = scrape_article(link)
                    published_at = parse_published_at(entry)

                    article = Article(
                        title=scraped["title"],
                        link=link,
                        published_at=published_at,
                        content=scraped["content"],
                        image_url=scraped["image_url"],
                        status="pending",
                        category=scraped["category"],
                        author=scraped["author"],
                        created_at=datetime.now(),
                    )

                    db.add(article)
                    db.commit()

                except Exception as e:
                    db.rollback()
                    print(f"Scrape failed for {link}: {e}")
                    continue

    finally:
        db.close()