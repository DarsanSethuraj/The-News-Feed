from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from database import SessionLocal
from models import Client, ClientCreate

from Authentication.admin_auth import verify_admin

import secrets
import json


router = APIRouter(
    prefix="/admin/add_client",
    tags=["Client Management"]
)


# =========================================================
# HARDCODED CATEGORIES
# =========================================================

CATEGORIES = [
    "World",
    "India",
    "Kerala",
    "Entertainment",
    "Gulf",
    "Tech",
    "Sports",
    "Crime",
    "Uncategorized"
]


# =========================================================
# CLIENT MANAGEMENT UI
# =========================================================

@router.get("", response_class=HTMLResponse)
def client_management_page(
    admin=Depends(verify_admin)
):

    categories_json = json.dumps(CATEGORIES)

    return f"""
<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Client Management</title>


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
            max-width: 900px;
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
            margin-bottom: 22px;
        }}


        label.title {{
            display: block;
            font-weight: bold;
            margin-bottom: 7px;
        }}


        input[type="text"],
        input[type="number"] {{
            width: 100%;
            padding: 11px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 15px;
        }}


        .help-text {{
            display: block;
            margin-top: 6px;
            font-size: 13px;
            color: #666;
        }}


        .categories {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-top: 10px;
        }}


        .category-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px;
            background: #f5f5f5;
            border-radius: 6px;
        }}


        .category-row:hover {{
            background: #e9e9e9;
        }}


        .category-checkbox {{
            width: 17px;
            height: 17px;
            cursor: pointer;
        }}


        .category-name {{
            flex: 1;
            font-weight: 500;
        }}


        .category-limit {{
            width: 90px !important;
            padding: 8px !important;
        }}


        .limit-label {{
            font-size: 12px;
            color: #666;
            white-space: nowrap;
        }}


        .active-box {{
            margin-top: 15px;
            margin-bottom: 25px;
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


        .api-key {{
            margin-top: 8px;
            padding: 12px;
            background: #eee;
            border-radius: 5px;
            font-family: monospace;
            word-break: break-all;
        }}


        .copy-button {{
            margin-top: 10px;
            background: #555;
        }}


        @media (max-width: 650px) {{

            body {{
                padding: 15px;
            }}


            .categories {{
                grid-template-columns: 1fr;
            }}


            .category-row {{
                flex-wrap: wrap;
            }}

        }}

    </style>

</head>


<body>


<div class="container">

    <div class="card">

        <h1>Add New Client</h1>


        <!-- CLIENT NAME -->

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


        <!-- API KEY -->

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
                Leave empty to generate one automatically.
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
                placeholder="example.com"
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
                value="25"
                min="1"
            >

            <span class="help-text">
                Overall maximum number of normal posts per day.
                Breaking news can exceed this limit.
            </span>

        </div>


        <!-- CATEGORIES -->

        <div class="field">

            <label class="title">
                Subscribed Categories
            </label>

            <span class="help-text">
                Select the categories this client can receive.
                Enter a category limit if you want to restrict
                how many normal posts from that category they
                can receive per day.
            </span>


            <div
                class="categories"
                id="categories"
            ></div>

        </div>


        <!-- ACTIVE -->

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


const categories = {categories_json};


// =========================================================
// CREATE CATEGORY UI
// =========================================================

function createCategoryFields() {{

    const container =
        document.getElementById("categories");


    categories.forEach(category => {{

        const row =
            document.createElement("div");


        row.className =
            "category-row";


        row.innerHTML = `

            <input
                type="checkbox"
                class="category-checkbox"
                value="${{category}}"
            >

            <span class="category-name">
                ${{category}}
            </span>

            <span class="limit-label">
                Limit:
            </span>

            <input
                type="number"
                class="category-limit"
                data-category="${{category}}"
                min="1"
                placeholder="None"
                disabled
            >

        `;


        const checkbox =
            row.querySelector(
                ".category-checkbox"
            );


        const limitInput =
            row.querySelector(
                ".category-limit"
            );


        checkbox.addEventListener(
            "change",
            function() {{

                limitInput.disabled =
                    !checkbox.checked;

                if (!checkbox.checked) {{

                    limitInput.value = "";

                }}

            }}
        );


        container.appendChild(row);

    }});

}}


// =========================================================
// GET CATEGORY DATA
// =========================================================

function getCategoryData() {{

    const selectedCategories = [];

    const categoryLimits = {{}};


    document
        .querySelectorAll(".category-row")
        .forEach(row => {{

            const checkbox =
                row.querySelector(
                    ".category-checkbox"
                );


            const limitInput =
                row.querySelector(
                    ".category-limit"
                );


            if (!checkbox.checked) {{
                return;
            }}


            const category =
                checkbox.value;


            selectedCategories.push(
                category
            );


            const limit =
                limitInput.value.trim();


            if (limit !== "") {{

                const numericLimit =
                    parseInt(limit);


                if (
                    !numericLimit ||
                    numericLimit < 1
                ) {{

                    throw new Error(
                        category +
                        " must have a valid limit."
                    );

                }}


                categoryLimits[category] =
                    numericLimit;

            }}

        }});


    return {{
        categories:
            selectedCategories,

        limits:
            categoryLimits
    }};

}}


// =========================================================
// CREATE CLIENT
// =========================================================

async function createClient() {{

    const button =
        document.getElementById(
            "create-button"
        );


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


    // -----------------------------------------------------
    // VALIDATION
    // -----------------------------------------------------

    if (!name) {{

        alert(
            "Please enter the client name."
        );

        return;

    }}


    if (!domain) {{

        alert(
            "Please enter the client domain."
        );

        return;

    }}


    if (
        !dailyLimit ||
        dailyLimit < 1
    ) {{

        alert(
            "Please enter a valid daily post limit."
        );

        return;

    }}


    let categoryData;


    try {{

        categoryData =
            getCategoryData();

    }}
    catch (error) {{

        alert(error.message);

        return;

    }}


    if (
        categoryData.categories.length === 0
    ) {{

        alert(
            "Please select at least one category."
        );

        return;

    }}


    // -----------------------------------------------------
    // DISABLE BUTTON
    // -----------------------------------------------------

    button.disabled = true;

    button.innerText =
        "Creating...";


    try {{

        const response =
            await fetch(
                "/admin/add_client",
                {{

                    method: "POST",

                    headers: {{

                        "Content-Type":
                            "application/json"

                    }},

                    body: JSON.stringify({{

                        name: name,

                        api_key:
                            apiKey || null,

                        allowed_domain:
                            domain,

                        daily_post_limit:
                            dailyLimit,

                        subscribed_categories:
                            categoryData.categories,

                        category_limits:
                            categoryData.limits,

                        active:
                            active

                    }})

                }}
            );


        const data =
            await response.json();


        const result =
            document.getElementById(
                "result"
            );


        result.style.display =
            "block";


        if (!response.ok) {{

            result.className =
                "error";


            result.innerHTML =
                "<strong>Error:</strong> " +
                (
                    data.detail ||
                    "Failed to create client."
                );


            return;

        }}


        result.className =
            "success";


        result.innerHTML = `

            <strong>
                Client created successfully.
            </strong>

            <p>
                <strong>Client:</strong>
                ${{escapeHtml(data.name)}}
            </p>

            <p>
                <strong>Domain:</strong>
                ${{escapeHtml(data.allowed_domain)}}
            </p>

            <p>
                <strong>Daily Limit:</strong>
                ${{data.daily_post_limit}}
            </p>

            <p>
                <strong>API Key:</strong>
            </p>

            <div
                class="api-key"
                id="generated-api-key"
            >
                ${{escapeHtml(data.api_key)}}
            </div>

            <button
                class="copy-button"
                onclick="copyApiKey()"
            >
                Copy API Key
            </button>

        `;


        // -------------------------------------------------
        // RESET FORM
        // -------------------------------------------------

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
                ".category-row"
            )
            .forEach(row => {{

                const checkbox =
                    row.querySelector(
                        ".category-checkbox"
                    );

                const limit =
                    row.querySelector(
                        ".category-limit"
                    );


                checkbox.checked =
                    false;

                limit.value = "";

                limit.disabled =
                    true;

            }});

    }}
    catch (error) {{

        const result =
            document.getElementById(
                "result"
            );


        result.style.display =
            "block";


        result.className =
            "error";


        result.innerHTML =
            "<strong>Error:</strong> " +
            "Could not connect to the server.";

    }}
    finally {{

        button.disabled = false;

        button.innerText =
            "Create Client";

    }}

}}


// =========================================================
// COPY API KEY
// =========================================================

function copyApiKey() {{

    const keyElement =
        document.getElementById(
            "generated-api-key"
        );


    if (!keyElement) {{
        return;
    }}


    navigator.clipboard
        .writeText(
            keyElement.innerText
        )
        .then(
            () => {{
                alert(
                    "API key copied."
                );
            }}
        );

}}


// =========================================================
// ESCAPE HTML
// =========================================================

function escapeHtml(value) {{

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        value;


    return div.innerHTML;

}}


// =========================================================
// START
// =========================================================

createCategoryFields();


</script>


</body>

</html>
"""


# =========================================================
# CREATE CLIENT API
# =========================================================

@router.post("")
def create_client(
    client_data: ClientCreate,
    admin=Depends(verify_admin)
):

    db = SessionLocal()

    try:

        # =================================================
        # CLEAN INPUT
        # =================================================

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


        # =================================================
        # VALIDATE NAME
        # =================================================

        if not name:

            raise HTTPException(
                status_code=400,
                detail="Client name is required."
            )


        # =================================================
        # VALIDATE DOMAIN
        # =================================================

        if not domain:

            raise HTTPException(
                status_code=400,
                detail="Client domain is required."
            )


        # =================================================
        # VALIDATE DAILY LIMIT
        # =================================================

        if client_data.daily_post_limit < 1:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Daily post limit "
                    "must be at least 1."
                )
            )


        # =================================================
        # VALIDATE CATEGORIES
        # =================================================

        if not client_data.subscribed_categories:

            raise HTTPException(
                status_code=400,
                detail=(
                    "At least one category "
                    "must be selected."
                )
            )


        invalid_categories = [

            category

            for category
            in client_data.subscribed_categories

            if category not in CATEGORIES

        ]


        if invalid_categories:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid categories: "
                    + ", ".join(
                        invalid_categories
                    )
                )
            )


        # =================================================
        # VALIDATE CATEGORY LIMITS
        # =================================================

        category_limits = (
            client_data.category_limits
            or {}
        )


        for category, limit in category_limits.items():

            if category not in CATEGORIES:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid category limit: "
                        f"{category}"
                    )
                )


            if category not in client_data.subscribed_categories:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Category limit specified "
                        f"for unsubscribed category: "
                        f"{category}"
                    )
                )


            if limit < 1:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Category limit for "
                        f"{category} must be at least 1."
                    )
                )


        # =================================================
        # CHECK DUPLICATE DOMAIN
        # =================================================

        existing_client = (

            db.query(Client)

            .filter(
                Client.allowed_domain
                == domain
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


        # =================================================
        # API KEY
        # =================================================

        if client_data.api_key:

            api_key = (
                client_data.api_key
                .strip()
            )

        else:

            api_key = secrets.token_hex(16)


        # =================================================
        # VALIDATE API KEY
        # =================================================

        if not api_key:

            raise HTTPException(
                status_code=400,
                detail="API key cannot be empty."
            )


        # =================================================
        # CHECK DUPLICATE API KEY
        # =================================================

        existing_api_key = (

            db.query(Client)

            .filter(
                Client.api_key
                == api_key
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


        # =================================================
        # SAVE CATEGORY LIMITS
        # =================================================

        category_limits_json = json.dumps(
            category_limits
        )


        # =================================================
        # CREATE CLIENT
        # =================================================

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

            category_limits=
                category_limits_json,

            active=
                client_data.active

        )


        db.add(client)

        db.commit()

        db.refresh(client)


        # =================================================
        # RETURN RESULT
        # =================================================

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

            "category_limits":
                category_limits,

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