import requests
from bs4 import BeautifulSoup
import json
import re


REMOVE_WORDS = [
    "മാധ്യമം",
    "madhyamam",
    "click here"
]


def clean_content(content: str):

    cleaned_lines = []

    for line in content.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        # Remove line if it contains unwanted words
        if any(
            word in stripped
            for word in REMOVE_WORDS
        ):
            continue

        cleaned_lines.append(stripped)

    return "\n\n".join(cleaned_lines).strip()

BANNED_PHRASES = [
    "read more",
    "advertisement",
    "newsletter",
    "subscribe",
    "click here",
    "malayalam",
    "മാധ്യമം",
    "madhyamam"
    ]

def madhyamam_scraper(url: str):

    if "video" in url or "/gallery/" in url or "/multimedia/" in url or "/webstories/" in url:
        raise Exception("Skipping video/gallery link")    
    
    if "fact-check" in url:
        raise Exception("Skipping fact-check link")
        

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    # Title
    title = soup.find("h1").get_text(strip=True) if soup.find("h1") else "No Title"

    # Category
    category = "Uncategorized"

    CATEGORY_MAP = {
        "India": [
            "/india/"
        ],

        "World": [
            "/world/"
        ],

        "Kerala": [
            "/kerala/",
            "/local-news/"
        ],

        "Entertainment": [
            "/entertainment/",

        ],

        "Sports": [
            "/sports/"
        ],

        "Gulf": [
            "/gulf-news/"
        ],

        "Crime": [
            "/crime/"
        ],

        "Tech": [
            "/technology/",
            "/science/"
        ]
    }

    for final_category, patterns in CATEGORY_MAP.items():

        if any(pattern in url for pattern in patterns):
            category = final_category
            break

    # Image
    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        image_url = og_image.get("content")

    if not image_url:
        raise Exception("No image found")


    # Content
    content = ""

    story_section = soup.find(
        "div",
        class_="story"
    )

    if not story_section:
        raise Exception("No story section found")


    BANNED_CLASSES = [
        "inside-post-ad",
        "ads_common_inside_post",
        "filler-ad-unit-inside-post"
    ]

    ALLOWED_TAGS = [
        "p",
        "h2",
        "h3",
        "ul",
        "ol",
        "li",
        "blockquote",
        "div"
    ]

    seen = set()

    for child in story_section.find_all(recursive=False):

        if child.name not in ALLOWED_TAGS:
            continue

        # Skip ad containers
        classes = child.get("class", [])

        if any(
            banned in classes
            for banned in BANNED_CLASSES
        ):
            continue

        text = child.get_text(" ", strip=True)

        if not text:
            continue

        lower = text.lower()

        # Skip promotional junk
        if any(
            phrase in lower
            for phrase in BANNED_PHRASES
        ):
            continue

        # Skip duplicate blocks
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

    # Try JSON-LD first
    """
    content = ""

    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string)

            if isinstance(data, dict) and "articleBody" in data:
                body = data["articleBody"]

                if body:
                    content = body.strip()

                break

        except Exception:
            continue
    """

    if title=="No Title":
        raise Exception("No title found")

    if not content:
        raise Exception("No content found")
    
    
    
    return {
        "title": title, 
        "content": content,
        "image_url": image_url,
        "category": category,
        "author": "Madhyamam"
    }
        
        