from database import SessionLocal
from models import Client

# This script is used to create a client in the database

# to create a client, run:
# docker compose exec backend python -m Client_Management.create_client


# docker compose exec db psql -U postgres -d newsdb
#then:
# \dt to see tables
# select * from clients; to see clients

db = SessionLocal()

client = Client(
    name="WordPress Playground",
    api_key="11a9798f0ff700d7fbcc47bd75c88384",
    daily_post_limit=25,
    subscribed_categories="World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime",
    allowed_domain="https://malayalam.business100news.com/",
    active=True
)

db.add(client)
db.commit()
db.close()
