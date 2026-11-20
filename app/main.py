"""FastAPI 애플리케이션 진입점."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from .api import tools, events, plans, agent

app = FastAPI(
    title="AI Fashion Planner API",
    description="자연어 조건에 맞는 패션 코디를 탐색하고 계획으로 관리하는 Agent 서비스",
    version="0.1.0",
)

origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(tools.router)
app.include_router(events.router)
app.include_router(plans.router)
app.include_router(agent.router)


@app.get("/health", tags=["health"], summary="서버 상태 확인")
def health_check():
    return {"status": "ok", "service": "ai-fashion-planner"}



@app.get("/", include_in_schema=False)
def frontend():
    """사용자용 프론트엔드 화면을 제공한다."""
    index_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return FileResponse(index_path)
