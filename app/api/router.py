"""Versioned API router composition."""

from fastapi import APIRouter

from app.api.routes.assessments import router as assessments_router
from app.api.routes.connectors import router as connectors_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.product import router as product_router

api_router = APIRouter()
api_router.include_router(connectors_router)
api_router.include_router(assessments_router)
api_router.include_router(knowledge_router)
api_router.include_router(product_router)
