from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.v1.router import api_router
from app.core.config import settings
from app.schemas import HealthRead


def generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "api"
    return f"{tag}_{route.name}".replace("-", "_")


app = FastAPI(
    title="Shift Planner API",
    version="0.1.0",
    generate_unique_id_function=generate_unique_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthRead, tags=["health"])
def health() -> HealthRead:
    return HealthRead(status="ok")


app.include_router(api_router)

