from fastapi import APIRouter, HTTPException
from database import SessionLocal
from pydantic import BaseModel
from typing import List
from models import Client
from models import DeliveryLog
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class DeliveryAckRequest(BaseModel):
    api_key: str
    article_ids: List[int]


router = APIRouter()

@router.post("/ack-delivery")
def acknowledge_delivery(payload: DeliveryAckRequest):
    db = SessionLocal()

    try:
        client = (
            db.query(Client)
            .filter(Client.api_key == payload.api_key)
            .first()
        )

        if not client:
            raise HTTPException(status_code=401, detail="Invalid API key")

        now = datetime.now(IST)

        for article_id in payload.article_ids:

            already_exists = (
                db.query(DeliveryLog)
                .filter(
                    DeliveryLog.client_id == client.id,
                    DeliveryLog.article_id == article_id
                )
                .first()
            )

            if already_exists:
                continue

            db.add(
                DeliveryLog(
                    client_id=client.id,
                    article_id=article_id,
                    delivered_at=now
                )
            )

        db.commit()

        return {
            "success": True,
            "acknowledged": payload.article_ids
        }

    finally:
        db.close()