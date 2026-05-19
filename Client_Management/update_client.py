from database import SessionLocal
from models import Client

# This script is used to update a client's information in the database

# to update a client, run:
# docker compose exec backend python -m Client_Management.update_client

API_KEY = "24c7cb6c062fed32036f72bdc0ccf10c" # replace with the actual API key of the client you want to update

db = SessionLocal()

client = db.query(Client).filter_by(api_key=API_KEY).first()

if not client:
    print("Client not found")
    db.close()
    exit()

client.daily_post_limit = 100
client.subscribed_categories = "World,India,Kerala,Entertainment,Gulf,Tech,Sports,Crime"
client.allowed_domain = "http://thenewsfeedin.local/"

db.commit()

print("Client updated successfully")

db.close()