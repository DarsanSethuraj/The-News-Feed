from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from database import Base
from datetime import datetime

from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    author = Column(String, nullable=True)

    title = Column(String, nullable=False)
    link = Column(String, unique=True, nullable=False)
    content = Column(Text)
    
    category = Column(String, default="None")
    image_url = Column(String)

    published_at = Column(DateTime)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(IST))

    is_breaking = Column(Boolean, default=False)

    show_25 = Column(Boolean, default=False)
    show_50 = Column(Boolean, default=False)
    show_100 = Column(Boolean, default=False)

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)

    name = Column(String, nullable=False)
    api_key = Column(String, unique=True)
    allowed_domain = Column(String, nullable=False)

    # Overall daily package limit
    daily_post_limit = Column(Integer, nullable=False)

    # Categories this client can receive
    subscribed_categories = Column(
        String,
        default="World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime,Uncategorized"
    )

    # Per-category normal-news limits
    #
    # Example:
    # {
    #     "Entertainment": 8,
    #     "Kerala": 10,
    #     "India": 10
    # }
    #
    # A category not present here has no category-specific limit.
    category_limits = Column(
        Text,
        default="{}"
    )

    active = Column(Boolean, default=True)

    activated_at = Column(
        DateTime,
        default=lambda: datetime.now(IST)
    )

    last_feed_request = Column(
        DateTime,
        nullable=True
    )

class DeliveryLog(Base):
    __tablename__ = "delivery_logs"

    id = Column(Integer, primary_key=True)

    client_id = Column(Integer)
    article_id = Column(Integer)

    delivered_at = Column(DateTime, default=lambda: datetime.now(IST))
    success = Column(Boolean, default=True)

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(
        String,
        unique=True,
        nullable=False
    )

    active = Column(
        Boolean,
        nullable=False,
        default=True
    )
    

from pydantic import BaseModel

class ArticleUpdate(BaseModel):
    title: str
    content: str



class CreateArticleRequest(BaseModel):
    title: str
    content: str
    category: str
    slug: str
    image_url: str | None = None


from typing import List

from typing import List, Dict


class ClientCreate(BaseModel):

    name: str

    api_key: str | None = None

    allowed_domain: str

    daily_post_limit: int

    subscribed_categories: List[str]

    category_limits: Dict[str, int] = {}

    active: bool = True
