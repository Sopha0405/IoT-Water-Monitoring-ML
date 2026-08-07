from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.init_db import init_db
from app.modules.alerts.router import router as alerts_router
from app.modules.auth.router import router as auth_router
from app.modules.devices.router import router as devices_router
from app.modules.floors.router import router as floors_router
from app.modules.ml_analysis.api.router import admin_router as ml_admin_router
from app.modules.ml_analysis.api.router import router as ml_analysis_router
from app.modules.ml_analysis.feedback.router import router as ml_feedback_router
from app.modules.notifications.router import router as notifications_router
from app.modules.roles.router import router as roles_router
from app.modules.telemetry.router import router as telemetry_router
from app.modules.users.router import router as users_router


app = FastAPI(title="Water Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(roles_router)
app.include_router(floors_router)
app.include_router(devices_router)
app.include_router(alerts_router)
app.include_router(ml_analysis_router, prefix="/ml")
app.include_router(ml_analysis_router, prefix="/api/v1/ml-analysis")
app.include_router(ml_admin_router)
app.include_router(ml_feedback_router)
app.include_router(notifications_router)
app.include_router(telemetry_router)
app.include_router(users_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
