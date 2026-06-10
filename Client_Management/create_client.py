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
    api_key="dc11f6aa715daf48a2014c88fa612df4",
    daily_post_limit=50,
    subscribed_categories="World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime",
    allowed_domain="https://playground.wordpress.net/",
    active=True
)

db.add(client)
db.commit()
db.close()
