import requests
from bs4 import BeautifulSoup
import json

import Scrapers.asianet_scraper
import Scrapers.madhyamam_scraper


BANNED_PHRASES = [
    "read more",
    "advertisement",
    "newsletter",
    "subscribe",
    ]

SCRAPER_REGISTRY = {
    "asianetnews.com": Scrapers.asianet_scraper.asianet_scraper,
    "madhyamam.com": Scrapers.madhyamam_scraper.madhyamam_scraper,
}

def scrape_article(url: str):

    
    for domain, scraper in SCRAPER_REGISTRY.items():
        if domain in url:
            return scraper(url)

    # Default scraper (basic)
    """
    else:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")

        # Title
        title = soup.find("h1").get_text(strip=True) if soup.find("h1") else "No Title"

        # Image
        image_url = None
        og_image = soup.find("meta", property="og:image")
        if og_image:
            image_url = og_image.get("content")

        # Content
        content = ""
        article_tag = soup.find("article")

        if article_tag:
            paragraphs = article_tag.find_all("p")
        else:
            paragraphs = soup.find_all("p")

        for p in paragraphs:
            text = p.get_text(strip=True).lower()
            if any(phrase in text for phrase in BANNED_PHRASES):
                continue
            content += p.get_text(strip=True) + "\n"

        return {
            "title": title,
            "content": content.strip(),
            "image_url": image_url,
            "category": "Uncategorized",
            "author": "No Author"
        }
    """