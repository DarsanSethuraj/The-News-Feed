import secrets

# This script is used to generate a new API key for a client

# to generate a new API key, run:
# docker compose exec backend python -m Client_Management.api_creation

api_key = secrets.token_hex(16)
print("API Key generated successfully")
print(f"API Key: {api_key}")