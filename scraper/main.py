import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from routers import query, cancel, credentials, email_templates, flor_depots, status_detail

app = FastAPI(title="반납컨테이너 스크래퍼 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(cancel.router)
app.include_router(credentials.router)
app.include_router(email_templates.router)
app.include_router(flor_depots.router)
app.include_router(status_detail.router)

@app.get("/")
def health():
    return {"status": "ok"}
