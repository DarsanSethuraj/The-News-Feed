from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from database import SessionLocal
from models import Client
from Authentication.admin_auth import verify_admin
from models import ClientCreate
import secrets


router = APIRouter(
    prefix="/admin/add_client",
    tags=["Client Management"]
)


# ---------------------------------------------------------
# Client management UI
# ---------------------------------------------------------

@router.get("", response_class=HTMLResponse)
def client_management_page(
    admin=Depends(verify_admin)
):

    return """
<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>Client Management</title>


    <style>

        * {
            box-sizing: border-box;
        }


        body {
            margin: 0;
            padding: 40px;
            font-family: Arial, sans-serif;
            background: #f5f6f8;
            color: #222;
        }


        .container {
            max-width: 850px;
            margin: auto;
        }


        .card {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 3px 15px rgba(0, 0, 0, 0.08);
        }


        h1 {
            margin-top: 0;
            margin-bottom: 25px;
        }


        .field {
            margin-bottom: 20px;
        }


        label.title {
            display: block;
            font-weight: bold;
            margin-bottom: 7px;
        }


        input[type="text"],
        input[type="number"] {
            width: 100%;
            padding: 11px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 15px;
        }


        .help-text {
            display: block;
            margin-top: 6px;
            font-size: 13px;
            color: #666;
        }


        .categories {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 10px;
        }


        .category {
            padding: 11px;
            background: #f5f5f5;
            border-radius: 6px;
            cursor: pointer;
        }


        .category:hover {
            background: #e9e9e9;
        }


        .active-box {
            margin-top: 15px;
        }


        button {
            border: none;
            background: #222;
            color: white;
            padding: 12px 22px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 15px;
        }


        button:hover {
            opacity: 0.85;
        }


        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }


        #result {
            display: none;
            margin-top: 25px;
            padding: 18px;
            border-radius: 8px;
        }


        .success {
            background: #e8f7e8;
            border: 1px solid #a7d9a7;
        }


        .error {
            background: #ffe8e8;
            border: 1px solid #e0aaaa;
        }


        .api-key {
            margin-top: 8px;
            padding: 12px;
            background: #eee;
            border-radius: 5px;
            font-family: monospace;
            word-break: break-all;
        }


        .copy-button {
            margin-top: 10px;
            background: #555;
        }


        @media (max-width: 650px) {

            body {
                padding: 15px;
            }


            .categories {
                grid-template-columns: 1fr 1fr;
            }

        }

    </style>

</head>


<body>


<div class="container">

    <div class="card">

        <h1>Add New Client</h1>


        <!-- Client Name -->

        <div class="field">

            <label class="title">
                Client Name
            </label>

            <input
                type="text"
                id="name"
                placeholder="Example: ABC News"
            >

        </div>


        <!-- API Key -->

        <div class="field">

            <label class="title">
                API Key
            </label>

            <input
                type="text"
                id="api_key"
                placeholder="Enter API key"
            >

            <span class="help-text">
                Enter an API key manually.
                Leave empty to generate one automatically.
            </span>

        </div>


        <!-- Domain -->

        <div class="field">

            <label class="title">
                Client Domain
            </label>

            <input
                type="text"
                id="domain"
                placeholder="example.com"
            >

        </div>


        <!-- Daily Limit -->

        <div class="field">

            <label class="title">
                Daily Post Limit
            </label>

            <input
                type="number"
                id="daily_limit"
                value="25"
                min="1"
            >

        </div>


        <!-- Categories -->

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


        <!-- Active -->

        <div class="active-box">

            <label>

                <input
                    type="checkbox"
                    id="active"
                    checked
                >

                Active

            </label>

        </div>


        <button
            id="create-button"
            onclick="createClient()"
        >
            Create Client
        </button>


        <div id="result"></div>


    </div>

</div>



<script>


async function createClient() {


    const button =
        document.getElementById("create-button");


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
    // Validation
    // -----------------------------------------------------

    if (!name) {

        alert(
            "Please enter the client name."
        );

        return;
    }


    if (!domain) {

        alert(
            "Please enter the client domain."
        );

        return;
    }


    if (!dailyLimit || dailyLimit < 1) {

        alert(
            "Please enter a valid daily post limit."
        );

        return;
    }


    if (categories.length === 0) {

        alert(
            "Please select at least one category."
        );

        return;
    }


    // -----------------------------------------------------
    // Disable button while creating
    // -----------------------------------------------------

    button.disabled = true;

    button.innerText = "Creating...";


    try {


        const response =
            await fetch(
                "/admin/add_client",
                {

                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({

                        name: name,

                        api_key:
                            apiKey || null,

                        allowed_domain:
                            domain,

                        daily_post_limit:
                            dailyLimit,

                        subscribed_categories:
                            categories,

                        active:
                            active

                    })

                }
            );


        const data =
            await response.json();


        const result =
            document.getElementById("result");


        result.style.display = "block";


        // -------------------------------------------------
        // Error
        // -------------------------------------------------

        if (!response.ok) {

            result.className = "error";

            result.innerHTML =
                "<strong>Error:</strong> " +
                (
                    data.detail ||
                    "Failed to create client."
                );

            return;
        }


        // -------------------------------------------------
        // Success
        // -------------------------------------------------

        result.className = "success";


        result.innerHTML = `

            <strong>
                Client created successfully.
            </strong>

            <p>
                <strong>Client:</strong>
                ${escapeHtml(data.name)}
            </p>

            <p>
                <strong>Domain:</strong>
                ${escapeHtml(data.allowed_domain)}
            </p>

            <p>
                <strong>API Key:</strong>
            </p>

            <div
                class="api-key"
                id="generated-api-key"
            >
                ${escapeHtml(data.api_key)}
            </div>

            <button
                class="copy-button"
                onclick="copyApiKey()"
            >
                Copy API Key
            </button>

            <p>
                Save this API key.
                It is required by the client's
                WordPress plugin.
            </p>

        `;


        // Clear form

        document
            .getElementById("name")
            .value = "";


        document
            .getElementById("api_key")
            .value = "";


        document
            .getElementById("domain")
            .value = "";


        document
            .getElementById("daily_limit")
            .value = "25";


        document
            .getElementById("active")
            .checked = true;


        document
            .querySelectorAll(
                '.category input[type="checkbox"]'
            )
            .forEach(
                checkbox => {
                    checkbox.checked = false;
                }
            );


    }

    catch (error) {

        const result =
            document.getElementById("result");


        result.style.display = "block";

        result.className = "error";

        result.innerHTML =
            "<strong>Error:</strong> " +
            "Could not connect to the server.";

    }

    finally {

        button.disabled = false;

        button.innerText = "Create Client";

    }

}



// ---------------------------------------------------------
// Copy API key
// ---------------------------------------------------------

function copyApiKey() {


    const keyElement =
        document.getElementById(
            "generated-api-key"
        );


    if (!keyElement) {
        return;
    }


    const key =
        keyElement.innerText;


    navigator.clipboard
        .writeText(key)
        .then(
            () => {
                alert("API key copied.");
            }
        );

}



// ---------------------------------------------------------
// Escape HTML
// ---------------------------------------------------------

function escapeHtml(value) {

    const div =
        document.createElement("div");

    div.textContent = value;

    return div.innerHTML;

}


</script>


</body>

</html>
"""


# ---------------------------------------------------------
# Create client
# ---------------------------------------------------------

@router.post("")
def create_client(
    client_data: ClientCreate,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        # -------------------------------------------------
        # Clean input
        # -------------------------------------------------

        name = (
            client_data.name
            .strip()
        )


        domain = (
            client_data.allowed_domain
            .strip()
            .lower()
            .replace("https://", "")
            .replace("http://", "")
            .replace("www.", "")
            .strip("/")
        )


        # -------------------------------------------------
        # Validate name
        # -------------------------------------------------

        if not name:

            raise HTTPException(
                status_code=400,
                detail="Client name is required."
            )


        # -------------------------------------------------
        # Validate domain
        # -------------------------------------------------

        if not domain:

            raise HTTPException(
                status_code=400,
                detail="Client domain is required."
            )


        # -------------------------------------------------
        # Validate daily limit
        # -------------------------------------------------

        if client_data.daily_post_limit < 1:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Daily post limit "
                    "must be at least 1."
                )
            )


        # -------------------------------------------------
        # Validate categories
        # -------------------------------------------------

        if not client_data.subscribed_categories:

            raise HTTPException(
                status_code=400,
                detail=(
                    "At least one category "
                    "must be selected."
                )
            )


        # -------------------------------------------------
        # Check duplicate domain
        # -------------------------------------------------

        existing_client = (
            db.query(Client)
            .filter(
                Client.allowed_domain == domain
            )
            .first()
        )


        if existing_client:

            raise HTTPException(
                status_code=400,
                detail=(
                    "A client with this "
                    "domain already exists."
                )
            )


        # -------------------------------------------------
        # API KEY
        #
        # If user entered one -> use it.
        #
        # If empty -> generate one.
        # -------------------------------------------------

        if client_data.api_key:

            api_key = (
                client_data.api_key
                .strip()
            )

        else:

            api_key = secrets.token_hex(16)


        # -------------------------------------------------
        # Validate API key
        # -------------------------------------------------

        if not api_key:

            raise HTTPException(
                status_code=400,
                detail="API key cannot be empty."
            )


        # -------------------------------------------------
        # Check duplicate API key
        # -------------------------------------------------

        existing_api_key = (
            db.query(Client)
            .filter(
                Client.api_key == api_key
            )
            .first()
        )


        if existing_api_key:

            raise HTTPException(
                status_code=400,
                detail=(
                    "This API key is already "
                    "assigned to another client."
                )
            )


        # -------------------------------------------------
        # Create client
        # -------------------------------------------------

        client = Client(

            name=name,

            api_key=api_key,

            allowed_domain=domain,

            daily_post_limit=(
                client_data.daily_post_limit
            ),

            subscribed_categories=(
                ",".join(
                    client_data.subscribed_categories
                )
            ),

            active=client_data.active

        )


        db.add(client)

        db.commit()

        db.refresh(client)


        # -------------------------------------------------
        # Return result
        # -------------------------------------------------

        return {

            "message":
                "Client created successfully",

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