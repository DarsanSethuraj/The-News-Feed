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
    name="Konni Vartha",
    api_key="5239f217dce3afa28945b3473c0ce20f",
    daily_post_limit=50,
    subscribed_categories="World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime",
    allowed_domain="https://konnivartha.in/",
    active=True
)

db.add(client)
db.commit()
db.close()
