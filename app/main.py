from dotenv import load_dotenv
from fastapi import FastAPI

from app.routers import chat, health, newsletters

load_dotenv()
app = FastAPI(
    title="GACHI-AI",
    version="0.1.0",
    docs_url="/ai/docs",
    redoc_url="/ai/redoc",
    openapi_url="/ai/openapi.json",
)

app.include_router(health.router)
app.include_router(newsletters.router)
app.include_router(chat.router)
