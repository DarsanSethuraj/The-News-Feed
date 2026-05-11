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

