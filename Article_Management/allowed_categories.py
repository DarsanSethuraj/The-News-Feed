from fastapi import APIRouter
from database import SessionLocal
from models import Client

router = APIRouter()


@router.get("/categories")
def get_categories(api_key: str):

    db = SessionLocal()

    client = db.query(Client).filter_by(
        api_key=api_key,
        active=True
    ).first()

    if not client:

        db.close()

        return {
            "error": "Invalid API key"
        }

    categories = [
        cat.strip()
        for cat in client.subscribed_categories.split(",")
        if cat.strip()
    ]

    db.close()

    return categories