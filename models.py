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
    created_at = Column(DateTime, default=datetime.now(IST))

    is_breaking = Column(Boolean, default=False)

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)

    name = Column(String, nullable=False)
    api_key = Column(String, unique=True)
    allowed_domain = Column(String, nullable=False)

    daily_post_limit = Column(Integer, nullable=False)
    subscribed_categories = Column(String, default="World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime,Uncategorized")

    active = Column(Boolean, default=True)
    activated_at = Column(DateTime, default=datetime.now(IST))

    last_feed_request = Column(DateTime, nullable=True) # for API response optimization

class DeliveryLog(Base):
    __tablename__ = "delivery_logs"

    id = Column(Integer, primary_key=True)

    client_id = Column(Integer)
    article_id = Column(Integer)

    delivered_at = Column(DateTime, default=datetime.now(IST))
    success = Column(Boolean, default=True)
    


