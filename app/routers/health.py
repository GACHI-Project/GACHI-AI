from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}
