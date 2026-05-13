import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from routers import query, credentials, email_templates

app = FastAPI(title="반납컨테이너 스크래퍼 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(credentials.router)
app.include_router(email_templates.router)

@app.get("/")
def health():
    return {"status": "ok"}
