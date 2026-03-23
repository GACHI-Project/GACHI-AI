from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="GACHI-AI", version="0.1.0")


class EchoRequest(BaseModel):
    text: str


@app.get("/ai/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ai/ping")
def ping() -> dict:
    return {"message": "pong"}


@app.post("/ai/echo")
def echo(req: EchoRequest) -> dict:
    return {"text": req.text}