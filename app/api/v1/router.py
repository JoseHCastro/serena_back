"""API v1 router — aggregates all module routers under /api/v1."""

from fastapi import APIRouter

from app.modules.alerts.router import router as alerts_router
from app.modules.auth.router import router as auth_router
from app.modules.biometric.router import router as biometric_router
from app.modules.media.router import router as media_router
from app.modules.patients.router import router as patients_router
from app.modules.reports.router import router as reports_router
from app.modules.sessions.router import router as sessions_router
from app.modules.users.router import router as users_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(patients_router)
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(biometric_router)
api_v1_router.include_router(media_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(alerts_router)
