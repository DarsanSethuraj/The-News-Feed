from fastapi import APIRouter
from database import SessionLocal
from models import Article

router = APIRouter()

@router.get("/pending-articles")
def get_pending_articles():
    
    db = SessionLocal()

    articles = db.query(Article).filter_by(status="pending").all()

    db.close()

    return articles
