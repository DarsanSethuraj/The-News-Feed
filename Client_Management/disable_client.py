from database import SessionLocal
from models import Client

# This script is used to disable a client in the database

# to disable a client, run:
# docker compose exec backend python -m Client_Management.disable_client

API_KEY = "24c7cb6c062fed32036f72bdc0ccf10c" # replace with the actual API key of the client you want to disable

db = SessionLocal()

client = db.query(Client).filter_by(api_key=API_KEY).first()

if not client:
    print("Client not found")
    db.close()
    exit()

client.active = True

db.commit()

print("Client disabled successfully")

db.close()