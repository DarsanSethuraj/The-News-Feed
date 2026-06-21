import requests
from bs4 import BeautifulSoup
import json
import re


REMOVE_WORDS = [
    "ലൈവ് കാണാന്‍",
    "ഏഷ്യാനെറ്റ്",
    "click here"
]

import re

import re

def clean_content(content: str):

    # Convert HTML spacing to paragraph breaks
    content = content.replace("&nbsp;", "\n")

    cleaned_paragraphs = []

    paragraphs = content.splitlines()

    for para in paragraphs:

        para = para.strip()

        if not para:
            continue

        sentences = re.split(r'(?<=[.!?।])\s+', para)

        cleaned_sentences = []

        for sentence in sentences:

            sentence = sentence.strip()

            if not sentence:
                continue

            if any(word in sentence for word in REMOVE_WORDS):
                continue

            cleaned_sentences.append(sentence)

        if cleaned_sentences:
            cleaned_paragraphs.append(" ".join(cleaned_sentences))

    return "\n\n".join(cleaned_paragraphs).strip()

BANNED_PHRASES = [
    "read more",
    "advertisement",
    "newsletter",
    "subscribe",
    "click here",
    "malayalam",
    "asianet",
    "ഏഷ്യാനെറ്റ്",
    ]

def asianet_scraper(url: str):

    if "video" in url or "/gallery/" in url or "/gulfroundup-program/" in url or "/webstories/" in url:
        raise Exception("Skipping video/gallery link")    
    
    if "fact-check" in url:
        raise Exception("Skipping fact-check link")
        

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    # Title
    title = soup.find("h1").get_text(strip=True) if soup.find("h1") else "No Title"

    # Category
    category = "Business"

    # Image
    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        image_url = og_image.get("content")

    if not image_url:
        raise Exception("No image found")


    # Content
    # Try JSON-LD first
    article_body = soup.find("div", itemprop="articleBody")

    if not article_body:
        raise Exception("No article body found")
    
    story_section = article_body.find(
        "section",
        id=lambda x: x and x.startswith("story_")
    )

    if not story_section:
        raise Exception("No story section found")

    content = ""
    seen = set()

    for child in story_section.find_all(recursive=False):

        text = child.get_text(" ", strip=True)

        if not text:
            continue

        lower = text.lower()

        if any(phrase in lower for phrase in BANNED_PHRASES):
            continue

        # Skip duplicates
        if text in seen:
            continue
        seen.add(text)

        if child.name in [
            "p",
            "h2",
            "h3",
            "ul",
            "ol",
            "li",
            "blockquote"
        ]:
            # Remove hyperlinks but keep text

            for a in child.find_all("a"):
                a.replace_with(a.get_text())
                
            content += str(child)


    if title=="No Title":
        raise Exception("No title found")
    """
    # remove LEAD + WON or similar patterns
    content = re.sub(r'^LEAD\s*\+\s*WON\s*', '', content)
    content = content.strip()

    content = clean_content(content)
    """
    if not content:
        raise Exception("No content found")
    
    
    
    return {
        "title": title, 
        "content": content,
        "image_url": image_url,
        "category": category,
        "author": "News 18"
    }
        
        