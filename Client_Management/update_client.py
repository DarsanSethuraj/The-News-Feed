from database import SessionLocal
from models import Client

# This script is used to update a client's information in the database

# to update a client, run:
# docker compose exec backend python -m Client_Management.update_client

API_KEY = "5239f217dce3afa28945b3473c0ce20f" # replace with the actual API key of the client you want to update

db = SessionLocal()

client = db.query(Client).filter_by(api_key=API_KEY).first()

if not client:
    print("Client not found")
    db.close()
    exit()

client.daily_post_limit = 25
client.subscribed_categories = "World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime"
client.allowed_domain = "https://konnivartha.in/"

db.commit()

print("Client updated successfully")

db.close()
