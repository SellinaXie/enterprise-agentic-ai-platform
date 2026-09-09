"""Versioned API router composition."""

from fastapi import APIRouter

from app.api.routes.assessments import router as assessments_router
from app.api.routes.knowledge import router as knowledge_router

api_router = APIRouter()
api_router.include_router(assessments_router)
api_router.include_router(knowledge_router)
