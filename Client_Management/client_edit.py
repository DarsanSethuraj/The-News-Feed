from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from database import SessionLocal
from models import Client

from Authentication.admin_auth import verify_admin

import json


router = APIRouter(
    prefix="/admin/edit_client",
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

            categories = (
                client.subscribed_categories
                or ""
            )


            if isinstance(
                categories,
                str
            ):

                categories = [

                    category.strip()

                    for category
                    in categories.split(",")

                    if category.strip()

                ]


            # ---------------------------------------------
            # Read category limits
            # ---------------------------------------------

            try:

                category_limits = json.loads(
                    client.category_limits
                    or "{}"
                )


                if not isinstance(
                    category_limits,
                    dict
                ):

                    category_limits = {}


            except (
                json.JSONDecodeError,
                TypeError
            ):

                category_limits = {}


            client_data.append({

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
                    categories,

                "category_limits":
                    category_limits,

                "active":
                    client.active

            })


        clients_json = json.dumps(
            client_data
        )


        categories_json = json.dumps(
            CATEGORIES
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
                grid-template-columns: 1fr;
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

        <div
            id="edit-form"
            style="display:none;"
        >


            <!-- NAME -->

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
                    Changing this will invalidate
                    the old API key.
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

                <span class="help-text">
                    Overall normal-news limit.
                    Breaking news can exceed this limit.
                </span>

            </div>


            <!-- CATEGORIES -->

            <div class="field">

                <label class="title">
                    Subscribed Categories
                </label>

                <span class="help-text">
                    Select the categories this client
                    can receive. Set a limit to restrict
                    normal posts from that category.
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

const categories = {categories_json};


// =========================================================
// CREATE CATEGORY UI
// =========================================================

function createCategoryFields() {{

    const container =
        document.getElementById(
            "categories"
        );


    categories.forEach(category => {{

        const row =
            document.createElement(
                "div"
            );


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
// POPULATE CLIENT DROPDOWN
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


        option.value =
            client.id;


        option.textContent =
            client.name +
            " — " +
            client.allowed_domain;


        select.appendChild(
            option
        );

    }});

}}


// =========================================================
// LOAD CLIENT
// =========================================================

function loadClient() {{

    const clientId =
        document
            .getElementById(
                "client_id"
            )
            .value;


    const form =
        document.getElementById(
            "edit-form"
        );


    if (!clientId) {{

        form.style.display =
            "none";

        return;

    }}


    const client =
        clients.find(
            c =>
                String(c.id)
                === String(clientId)
        );


    if (!client) {{

        form.style.display =
            "none";

        return;

    }}


    // -----------------------------------------------------
    // Basic fields
    // -----------------------------------------------------

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


    // -----------------------------------------------------
    // Clear category fields
    // -----------------------------------------------------

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


            limit.value =
                "";


            limit.disabled =
                true;

        }});


    // -----------------------------------------------------
    // Load subscribed categories
    // -----------------------------------------------------

    const subscribed =
        client.subscribed_categories
        || [];


    const limits =
        client.category_limits
        || {{}};


    document
        .querySelectorAll(
            ".category-row"
        )
        .forEach(row => {{

            const checkbox =
                row.querySelector(
                    ".category-checkbox"
                );


            const limitInput =
                row.querySelector(
                    ".category-limit"
                );


            const category =
                checkbox.value;


            if (
                subscribed.includes(
                    category
                )
            ) {{

                checkbox.checked =
                    true;


                limitInput.disabled =
                    false;


                if (
                    limits[category] !== undefined
                ) {{

                    limitInput.value =
                        limits[category];

                }}

            }}

        }});


    form.style.display =
        "block";


    document
        .getElementById("result")
        .style.display =
        "none";

}}


// =========================================================
// GET CATEGORY DATA
// =========================================================

function getCategoryData() {{

    const selectedCategories = [];

    const categoryLimits = {{}};


    document
        .querySelectorAll(
            ".category-row"
        )
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
// UPDATE CLIENT
// =========================================================

async function updateClient() {{

    const clientId =
        document
            .getElementById(
                "client_id"
            )
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
                .getElementById(
                    "daily_limit"
                )
                .value
        );


    const active =
        document
            .getElementById("active")
            .checked;


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


    const button =
        document.getElementById(
            "save-button"
        );


    button.disabled =
        true;


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

                        api_key:
                            apiKey,

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
                    "Failed to update client."
                );


            return;

        }}


        result.className =
            "success";


        result.innerHTML =
            "<strong>" +
            "Client updated successfully." +
            "</strong>";


        // -------------------------------------------------
        // Update local data
        // -------------------------------------------------

        const index =
            clients.findIndex(
                c =>
                    String(c.id)
                    === String(clientId)
            );


        if (index !== -1) {{

            clients[index] = {{

                id:
                    Number(clientId),

                name:
                    name,

                api_key:
                    apiKey,

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

            }};

        }}


        // -------------------------------------------------
        // Update dropdown
        // -------------------------------------------------

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


        result.style.display =
            "block";


        result.className =
            "error";


        result.innerHTML =
            "<strong>Error:</strong> " +
            "Could not connect to the server.";

    }}
    finally {{

        button.disabled =
            false;


        button.innerText =
            "Save Changes";

    }}

}}


// =========================================================
// START
// =========================================================

createCategoryFields();

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

        # =================================================
        # FIND CLIENT
        # =================================================

        client = (

            db.query(Client)

            .filter(
                Client.id
                == client_id
            )

            .first()

        )


        if not client:

            raise HTTPException(
                status_code=404,
                detail="Client not found."
            )


        # =================================================
        # GET VALUES
        # =================================================

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


        try:

            daily_limit = int(
                client_data.get(
                    "daily_post_limit",
                    0
                )
            )

        except (
            ValueError,
            TypeError
        ):

            daily_limit = 0


        categories = client_data.get(
            "subscribed_categories",
            []
        )


        category_limits = client_data.get(
            "category_limits",
            {}
        )


        active = bool(
            client_data.get(
                "active",
                False
            )
        )


        # =================================================
        # VALIDATION
        # =================================================

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


        # =================================================
        # VALIDATE CATEGORIES
        # =================================================

        invalid_categories = [

            category

            for category in categories

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

        if not isinstance(
            category_limits,
            dict
        ):

            raise HTTPException(
                status_code=400,
                detail="Invalid category limits."
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


            if category not in categories:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Category limit specified "
                        f"for unsubscribed category: "
                        f"{category}"
                    )
                )


            try:

                limit = int(limit)

            except (
                ValueError,
                TypeError
            ):

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid limit for "
                        f"{category}."
                    )
                )


            if limit < 1:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Category limit for "
                        f"{category} must be "
                        f"at least 1."
                    )
                )


        # =================================================
        # CHECK DUPLICATE DOMAIN
        # =================================================

        duplicate_domain = (

            db.query(Client)

            .filter(

                Client.allowed_domain
                == domain,

                Client.id
                != client_id

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


        # =================================================
        # CHECK DUPLICATE API KEY
        # =================================================

        duplicate_api_key = (

            db.query(Client)

            .filter(

                Client.api_key
                == api_key,

                Client.id
                != client_id

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


        # =================================================
        # SAVE
        # =================================================

        client.name = name

        client.api_key = api_key

        client.allowed_domain = domain

        client.daily_post_limit = daily_limit

        client.subscribed_categories = (
            ",".join(categories)
        )

        client.category_limits = (
            json.dumps(
                category_limits
            )
        )

        client.active = active


        db.commit()

        db.refresh(client)


        # =================================================
        # RESPONSE
        # =================================================

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