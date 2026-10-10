from database import SessionLocal
from models import Client

import json


# =========================================================
# CLIENT TO UPDATE
# =========================================================

API_KEY = "REPLACE_WITH_CLIENT_API_KEY"


# =========================================================
# CLIENT SETTINGS
# =========================================================

CLIENT_NAME = "Business 100 News"

DAILY_POST_LIMIT = 25

ALLOWED_DOMAIN = "https://malayalam.business100news.com/"


# =========================================================
# SUBSCRIBED CATEGORIES
# =========================================================

SUBSCRIBED_CATEGORIES = [
    "World",
    "India",
    "Kerala",
    "Entertainment",
    "Gulf",
    "Tech",
    "Sports",
    "Crime"
]


# =========================================================
# CATEGORY LIMITS
#
# Leave a category out of this dictionary if you want
# that category to have no specific category limit.
#
# Example:
#
# Entertainment = 8
# Kerala        = 10
# India         = 5
#
# The overall DAILY_POST_LIMIT still applies.
#
# Breaking news is not restricted by these limits.
# =========================================================

CATEGORY_LIMITS = {
    "Entertainment": 8,
    "Kerala": 10,
    "India": 5
}


# =========================================================
# UPDATE CLIENT
# =========================================================

db = SessionLocal()


try:

    # -----------------------------------------------------
    # Find client
    # -----------------------------------------------------

    client = (
        db.query(Client)
        .filter_by(
            api_key=API_KEY
        )
        .first()
    )


    if not client:

        print("Client not found")

        exit()


    # -----------------------------------------------------
    # Validate category limits
    # -----------------------------------------------------

    for category, limit in CATEGORY_LIMITS.items():

        if category not in SUBSCRIBED_CATEGORIES:

            print(
                f"ERROR: {category} has a limit "
                "but is not subscribed."
            )

            exit()


        if not isinstance(
            limit,
            int
        ) or limit < 1:

            print(
                f"ERROR: Invalid limit for "
                f"{category}: {limit}"
            )

            exit()


    # -----------------------------------------------------
    # Update basic information
    # -----------------------------------------------------

    client.name = CLIENT_NAME

    client.daily_post_limit = (
        DAILY_POST_LIMIT
    )

    client.subscribed_categories = (
        ",".join(
            SUBSCRIBED_CATEGORIES
        )
    )

    client.allowed_domain = (
        ALLOWED_DOMAIN
    )


    # -----------------------------------------------------
    # Update category limits
    # -----------------------------------------------------

    client.category_limits = json.dumps(
        CATEGORY_LIMITS
    )


    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    db.commit()

    db.refresh(client)


    # -----------------------------------------------------
    # Display result
    # -----------------------------------------------------

    print(
        "Client updated successfully"
    )

    print(
        f"Client: {client.name}"
    )

    print(
        f"Daily limit: "
        f"{client.daily_post_limit}"
    )

    print(
        f"Categories: "
        f"{client.subscribed_categories}"
    )

    print(
        f"Category limits: "
        f"{client.category_limits}"
    )


finally:

    db.close()