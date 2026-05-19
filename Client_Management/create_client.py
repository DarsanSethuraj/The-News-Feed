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
    name="Test Client",
    api_key="24c7cb6c062fed32036f72bdc0ccf10c",
    daily_post_limit=30,
    subscribed_categories="World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime",
    allowed_domain="clientsite.com",
    active=True
)

db.add(client)
db.commit()
db.close()
