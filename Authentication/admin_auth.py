from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends
import secrets

security = HTTPBasic()

import os

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def verify_admin(
    credentials: HTTPBasicCredentials = Depends(security)
):

    correct_username = secrets.compare_digest(
        credentials.username,
        ADMIN_USERNAME
    )

    correct_password = secrets.compare_digest(
        credentials.password,
        ADMIN_PASSWORD
    )

    if not (
        correct_username and correct_password
    ):

        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )