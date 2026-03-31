from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routes.extract import router as extract_router


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": f"{settings.app_name} is running!"
    }


@app.get("/health")
async def app_health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(extract_router)


@app.exception_handler(Exception)
async def global_exception_handler(_, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"An unexpected error occurred: {str(exc)}"
        },
    )
