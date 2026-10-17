from fastapi import FastAPI



from Article_Management.articles import router as articles_router

from Article_Management.approve import router as approve_router

from Article_Management.reject import router as reject_router

from Article_Management.breaking import router as breaking_router

from Article_Management.pending_articles import router as pending_articles_router

from Article_Management.client_feed import router as client_feed_router

from Article_Management.allowed_categories import router as allowed_categories_router

from Article_Management.ack_delivery import router as ack_delivery_router

from Dashboard.client_dashboard import router as client_dashboard_router

from Dashboard.article_approval import router as article_approval_router

from Article_Management.update_article import router as update_article_router

from Dashboard.create_article import router as create_article_router

from Client_Management.client_creation import router as client_management_router

from Client_Management.client_edit import router as edit_client_router


app = FastAPI()


app.include_router(articles_router)

app.include_router(pending_articles_router)

app.include_router(approve_router)

app.include_router(reject_router)

app.include_router(breaking_router)

app.include_router(client_feed_router)

app.include_router(article_approval_router)

app.include_router(allowed_categories_router)

app.include_router(ack_delivery_router)

app.include_router(client_dashboard_router)

app.include_router(update_article_router)

app.include_router(create_article_router)

app.include_router(client_management_router)

app.include_router(edit_client_router)

app.include_router(rewrite_article_router)