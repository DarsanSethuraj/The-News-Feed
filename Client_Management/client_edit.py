from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from database import SessionLocal
from models import Client
from Authentication.admin_auth import verify_admin


router = APIRouter(
    prefix="/admin/edit_client",
    tags=["Client Management"]
)


# =========================================================
# EDIT CLIENT PAGE
# =========================================================

@router.get("", response_class=HTMLResponse)
def edit_client_page(
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        clients = (
            db.query(Client)
            .order_by(Client.id.asc())
            .all()
        )

        client_data = []

        for client in clients:

            categories = client.subscribed_categories or ""

            if isinstance(categories, str):
                categories = [
                    category.strip()
                    for category in categories.split(",")
                    if category.strip()
                ]

            client_data.append({
                "id": client.id,
                "name": client.name,
                "api_key": client.api_key,
                "allowed_domain": client.allowed_domain,
                "daily_post_limit": client.daily_post_limit,
                "subscribed_categories": categories,
                "active": client.active
            })


        import json

        clients_json = json.dumps(
            client_data
        )


        return f"""
<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Edit Client</title>


    <style>

        * {{
            box-sizing: border-box;
        }}


        body {{
            margin: 0;
            padding: 40px;
            font-family: Arial, sans-serif;
            background: #f5f6f8;
            color: #222;
        }}


        .container {{
            max-width: 850px;
            margin: auto;
        }}


        .card {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 3px 15px rgba(0, 0, 0, 0.08);
        }}


        h1 {{
            margin-top: 0;
            margin-bottom: 25px;
        }}


        .field {{
            margin-bottom: 20px;
        }}


        label.title {{
            display: block;
            font-weight: bold;
            margin-bottom: 7px;
        }}


        select,
        input[type="text"],
        input[type="number"] {{
            width: 100%;
            padding: 11px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 15px;
        }}


        select {{
            background: white;
        }}


        .help-text {{
            display: block;
            margin-top: 6px;
            font-size: 13px;
            color: #666;
        }}


        .categories {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 10px;
        }}


        .category {{
            padding: 11px;
            background: #f5f5f5;
            border-radius: 6px;
            cursor: pointer;
        }}


        .category:hover {{
            background: #e9e9e9;
        }}


        .active-box {{
            margin-top: 15px;
            margin-bottom: 30px;
        }}


        button {{
            border: none;
            background: #222;
            color: white;
            padding: 12px 22px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 15px;
        }}


        button:hover {{
            opacity: 0.85;
        }}


        button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}


        #result {{
            display: none;
            margin-top: 25px;
            padding: 18px;
            border-radius: 8px;
        }}


        .success {{
            background: #e8f7e8;
            border: 1px solid #a7d9a7;
        }}


        .error {{
            background: #ffe8e8;
            border: 1px solid #e0aaaa;
        }}


        @media (max-width: 650px) {{

            body {{
                padding: 15px;
            }}


            .categories {{
                grid-template-columns: 1fr 1fr;
            }}

        }}

    </style>

</head>


<body>


<div class="container">

    <div class="card">

        <h1>Edit Client</h1>


        <!-- CLIENT SELECT -->

        <div class="field">

            <label class="title">
                Select Client
            </label>


            <select
                id="client_id"
                onchange="loadClient()"
            >

                <option value="">
                    -- Select a client --
                </option>

            </select>

        </div>


        <!-- EDIT FORM -->

        <div id="edit-form" style="display:none;">


            <!-- CLIENT NAME -->

            <div class="field">

                <label class="title">
                    Client Name
                </label>

                <input
                    type="text"
                    id="name"
                >

            </div>


            <!-- API KEY -->

            <div class="field">

                <label class="title">
                    API Key
                </label>

                <input
                    type="text"
                    id="api_key"
                >

                <span class="help-text">
                    Changing this will invalidate the old API key.
                </span>

            </div>


            <!-- DOMAIN -->

            <div class="field">

                <label class="title">
                    Client Domain
                </label>

                <input
                    type="text"
                    id="domain"
                >

            </div>


            <!-- DAILY LIMIT -->

            <div class="field">

                <label class="title">
                    Daily Post Limit
                </label>

                <input
                    type="number"
                    id="daily_limit"
                    min="1"
                >

            </div>


            <!-- CATEGORIES -->

            <div class="field">

                <label class="title">
                    Subscribed Categories
                </label>


                <div class="categories">


                    <label class="category">

                        <input
                            type="checkbox"
                            value="World"
                        >

                        World

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="India"
                        >

                        India

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Kerala"
                        >

                        Kerala

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Entertainment"
                        >

                        Entertainment

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Gulf"
                        >

                        Gulf

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Tech"
                        >

                        Tech

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Sports"
                        >

                        Sports

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Crime"
                        >

                        Crime

                    </label>


                    <label class="category">

                        <input
                            type="checkbox"
                            value="Uncategorized"
                        >

                        Uncategorized

                    </label>


                </div>

            </div>


            <!-- ACTIVE -->

            <div class="active-box">

                <label>

                    <input
                        type="checkbox"
                        id="active"
                    >

                    Active

                </label>

            </div>


            <button
                id="save-button"
                onclick="updateClient()"
            >
                Save Changes
            </button>


        </div>


        <div id="result"></div>


    </div>

</div>



<script>


const clients = {clients_json};


// =========================================================
// LOAD CLIENT DROPDOWN
// =========================================================

function populateClients() {{

    const select =
        document.getElementById(
            "client_id"
        );


    clients.forEach(client => {{

        const option =
            document.createElement(
                "option"
            );


        option.value = client.id;


        option.textContent =
            client.name +
            " — " +
            client.allowed_domain;


        select.appendChild(option);

    }});

}}



// =========================================================
// LOAD SELECTED CLIENT
// =========================================================

function loadClient() {{

    const clientId =
        document
            .getElementById("client_id")
            .value;


    const form =
        document.getElementById(
            "edit-form"
        );


    if (!clientId) {{

        form.style.display = "none";

        return;

    }}


    const client =
        clients.find(
            c => String(c.id) === String(clientId)
        );


    if (!client) {{

        form.style.display = "none";

        return;

    }}


    document
        .getElementById("name")
        .value =
        client.name || "";


    document
        .getElementById("api_key")
        .value =
        client.api_key || "";


    document
        .getElementById("domain")
        .value =
        client.allowed_domain || "";


    document
        .getElementById("daily_limit")
        .value =
        client.daily_post_limit || 1;


    document
        .getElementById("active")
        .checked =
        client.active === true;


    // Clear categories first

    document
        .querySelectorAll(
            '.category input[type="checkbox"]'
        )
        .forEach(
            checkbox => {{
                checkbox.checked = false;
            }}
        );


    // Select client's categories

    const categories =
        client.subscribed_categories || [];


    document
        .querySelectorAll(
            '.category input[type="checkbox"]'
        )
        .forEach(
            checkbox => {{

                checkbox.checked =
                    categories.includes(
                        checkbox.value
                    );

            }}
        );


    form.style.display = "block";


    document
        .getElementById("result")
        .style.display = "none";

}}



// =========================================================
// UPDATE CLIENT
// =========================================================

async function updateClient() {{

    const clientId =
        document
            .getElementById("client_id")
            .value;


    if (!clientId) {{

        alert(
            "Please select a client."
        );

        return;

    }}


    const name =
        document
            .getElementById("name")
            .value
            .trim();


    const apiKey =
        document
            .getElementById("api_key")
            .value
            .trim();


    const domain =
        document
            .getElementById("domain")
            .value
            .trim();


    const dailyLimit =
        parseInt(
            document
                .getElementById("daily_limit")
                .value
        );


    const active =
        document
            .getElementById("active")
            .checked;


    const categories =
        Array.from(
            document.querySelectorAll(
                '.category input[type="checkbox"]:checked'
            )
        ).map(
            checkbox => checkbox.value
        );


    // -----------------------------------------------------
    // VALIDATION
    // -----------------------------------------------------

    if (!name) {{

        alert(
            "Please enter the client name."
        );

        return;

    }}


    if (!apiKey) {{

        alert(
            "API key cannot be empty."
        );

        return;

    }}


    if (!domain) {{

        alert(
            "Please enter the client domain."
        );

        return;

    }}


    if (!dailyLimit || dailyLimit < 1) {{

        alert(
            "Please enter a valid daily post limit."
        );

        return;

    }}


    if (categories.length === 0) {{

        alert(
            "Please select at least one category."
        );

        return;

    }}


    const button =
        document.getElementById(
            "save-button"
        );


    button.disabled = true;

    button.innerText =
        "Saving...";


    try {{

        const response =
            await fetch(
                "/admin/edit_client/" +
                clientId,
                {{

                    method: "PUT",

                    headers: {{

                        "Content-Type":
                            "application/json"

                    }},

                    body: JSON.stringify({{

                        name: name,

                        api_key: apiKey,

                        allowed_domain: domain,

                        daily_post_limit:
                            dailyLimit,

                        subscribed_categories:
                            categories,

                        active: active

                    }})

                }}
            );


        const data =
            await response.json();


        const result =
            document.getElementById(
                "result"
            );


        result.style.display = "block";


        if (!response.ok) {{

            result.className = "error";


            result.innerHTML =
                "<strong>Error:</strong> " +
                (
                    data.detail ||
                    "Failed to update client."
                );


            return;

        }}


        result.className = "success";


        result.innerHTML =
            "<strong>Client updated successfully.</strong>";


        // Update local client data

        const index =
            clients.findIndex(
                c =>
                    String(c.id) ===
                    String(clientId)
            );


        if (index !== -1) {{

            clients[index] = {{

                id:
                    Number(clientId),

                name: name,

                api_key: apiKey,

                allowed_domain: domain,

                daily_post_limit:
                    dailyLimit,

                subscribed_categories:
                    categories,

                active: active

            }};

        }}


        // Update dropdown text

        const option =
            document.querySelector(
                '#client_id option[value="' +
                clientId +
                '"]'
            );


        if (option) {{

            option.textContent =
                name +
                " — " +
                domain;

        }}


    }}

    catch (error) {{

        const result =
            document.getElementById(
                "result"
            );


        result.style.display = "block";

        result.className = "error";


        result.innerHTML =
            "<strong>Error:</strong> " +
            "Could not connect to the server.";

    }}

    finally {{

        button.disabled = false;

        button.innerText =
            "Save Changes";

    }}

}}


// =========================================================
// START
// =========================================================

populateClients();


</script>


</body>

</html>
"""


    finally:

        db.close()


# =========================================================
# UPDATE CLIENT API
# =========================================================

@router.put("/{client_id}")
def update_client(
    client_id: int,
    client_data: dict,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        client = (
            db.query(Client)
            .filter(
                Client.id == client_id
            )
            .first()
        )


        if not client:

            raise HTTPException(
                status_code=404,
                detail="Client not found."
            )


        # -------------------------------------------------
        # Get values
        # -------------------------------------------------

        name = str(
            client_data.get(
                "name",
                ""
            )
        ).strip()


        api_key = str(
            client_data.get(
                "api_key",
                ""
            )
        ).strip()


        domain = str(
            client_data.get(
                "allowed_domain",
                ""
            )
        ).strip().lower()


        domain = (
            domain
            .replace("https://", "")
            .replace("http://", "")
            .replace("www.", "")
            .strip("/")
        )


        daily_limit = int(
            client_data.get(
                "daily_post_limit",
                0
            )
        )


        categories = client_data.get(
            "subscribed_categories",
            []
        )


        active = bool(
            client_data.get(
                "active",
                False
            )
        )


        # -------------------------------------------------
        # Validation
        # -------------------------------------------------

        if not name:

            raise HTTPException(
                status_code=400,
                detail="Client name is required."
            )


        if not api_key:

            raise HTTPException(
                status_code=400,
                detail="API key cannot be empty."
            )


        if not domain:

            raise HTTPException(
                status_code=400,
                detail="Client domain is required."
            )


        if daily_limit < 1:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Daily post limit "
                    "must be at least 1."
                )
            )


        if not categories:

            raise HTTPException(
                status_code=400,
                detail=(
                    "At least one category "
                    "must be selected."
                )
            )


        # -------------------------------------------------
        # Check duplicate domain
        #
        # Exclude the current client.
        # -------------------------------------------------

        duplicate_domain = (
            db.query(Client)
            .filter(
                Client.allowed_domain == domain,
                Client.id != client_id
            )
            .first()
        )


        if duplicate_domain:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Another client is already "
                    "using this domain."
                )
            )


        # -------------------------------------------------
        # Check duplicate API key
        #
        # Exclude the current client.
        # -------------------------------------------------

        duplicate_api_key = (
            db.query(Client)
            .filter(
                Client.api_key == api_key,
                Client.id != client_id
            )
            .first()
        )


        if duplicate_api_key:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Another client is already "
                    "using this API key."
                )
            )


        # -------------------------------------------------
        # Update client
        # -------------------------------------------------

        client.name = name

        client.api_key = api_key

        client.allowed_domain = domain

        client.daily_post_limit = daily_limit

        client.subscribed_categories = ",".join(
            categories
        )

        client.active = active


        db.commit()

        db.refresh(client)


        return {

            "message":
                "Client updated successfully",

            "id":
                client.id,

            "name":
                client.name,

            "api_key":
                client.api_key,

            "allowed_domain":
                client.allowed_domain,

            "daily_post_limit":
                client.daily_post_limit,

            "subscribed_categories":
                client.subscribed_categories,

            "active":
                client.active

        }


    except HTTPException:

        db.rollback()

        raise


    except Exception as e:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


    finally:

        db.close()