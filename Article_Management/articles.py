from database import SessionLocal
from models import Article
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return {"message": "Backend Running"}


@router.get("/articles")
def get_articles():
    
    db = SessionLocal()
    articles = db.query(Article).all()
    db.close()

    return articles