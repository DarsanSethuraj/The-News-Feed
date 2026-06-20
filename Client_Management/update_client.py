from database import SessionLocal
from models import Client

# This script is used to update a client's information in the database

# to update a client, run:
# docker compose exec backend python -m Client_Management.update_client

API_KEY = "11a9798f0ff700d7fbcc47bd75c88384" # replace with the actual API key of the client you want to update

db = SessionLocal()

client = db.query(Client).filter_by(api_key=API_KEY).first()

if not client:
    print("Client not found")
    db.close()
    exit()

client.name = "Business 100 News"
client.daily_post_limit = 25
client.subscribed_categories = "World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime"
client.allowed_domain = "https://malayalam.business100news.com/"

db.commit()

print("Client updated successfully")

db.close()
