from celery_app import celery
import feedparser
from database import SessionLocal
from models import Article

from scraper import scrape_article

FEEDS = [
    "https://www.asianetnews.com/rss",
    "https://www.madhyamam.com/feeds.xml"
]

@celery.task
def fetch_all_feeds():
    db = SessionLocal()

    try:
        for url in FEEDS:
            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:

                if "/videos/" in entry.link or "/gallery/" in entry.link:
                    continue

                existing = db.query(Article).filter_by(link=entry.link).first()
                if existing:
                    continue
                
                try:
                    scraped = scrape_article(entry.link)
                    
                    article = Article(
                        title=scraped["title"],
                        link=entry.link,
                        published_at=entry.get("published"),
                        content=scraped["content"],
                        image_url=scraped["image_url"],
                        status="pending",
                        category=scraped["category"],
                        author=scraped["author"]
                    )

                    db.add(article)
                    
                except Exception as e:
                    print(f"Scrape failed for {entry.link}: {e}")
                    continue

        db.commit()

    finally:
        db.close()