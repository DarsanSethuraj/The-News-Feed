from database import SessionLocal
from models import Client

# This script is used to disable a client in the database

# to disable a client, run:
# docker compose exec backend python -m Client_Management.disable_client

API_KEY = "dc11f6aa715daf48a2014c88fa612df4" # replace with the actual API key of the client you want to disable

db = SessionLocal()

client = db.query(Client).filter_by(api_key=API_KEY).first()

if not client:
    print("Client not found")
    db.close()
    exit()

client.active = False

db.commit()

print("Client disabled successfully")

db.close()