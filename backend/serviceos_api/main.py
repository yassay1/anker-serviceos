from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from serviceos_api.api.health import router as health_router
from serviceos_api.api.business import router as business_router
from serviceos_api.api.resources import router as resources_router
from serviceos_api.api.evidence import router as evidence_router
from serviceos_api.api.actions import router as actions_router
from serviceos_api.api.verification import router as verification_router
from serviceos_api.api.followups import router as followups_router
from serviceos_api.api.skills import router as skills_router
from serviceos_api.api.experience import router as experience_router
from serviceos_api.api.knowledge import router as knowledge_router
from serviceos_api.api.guard import router as guard_router
from serviceos_api.application.errors import ServiceError
from serviceos_api.observability import configure_logging, observe_request
from serviceos_api.settings import Settings


def create_app(*, database_engine=None, settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        configure_logging()
        yield
        if application.state.owns_engine and application.state.database_engine is not None:
            application.state.database_engine.dispose()

    application = FastAPI(
        title="Anker ServiceOS API",
        version="0.1.0",
        description="V1 business foundation. Local authentication is explicit and development-only. Agent jobs run only in a separately started Worker with an explicitly configured model provider.",
        lifespan=lifespan,
    )
    application.state.database_engine = database_engine
    application.state.owns_engine = False
    application.state.settings = settings or Settings.from_environment()

    @application.middleware("http")
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in ("POST", "PATCH", "DELETE", "PUT") and origin and origin not in application.state.settings.allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "不能受理来自该网站的修改请求。"})
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        body = {"detail": error.detail}
        if error.code:
            body["code"] = error.code
        if error.current_version is not None:
            body["current_version"] = error.current_version
        return JSONResponse(status_code=error.status, content=body)

    @application.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error: IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "请求与当前记录冲突，请刷新后重试。"})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "业务数据库暂不可用。"})

    application.middleware("http")(observe_request)
    application.include_router(health_router)
    application.include_router(business_router)
    application.include_router(resources_router)
    application.include_router(evidence_router)
    application.include_router(actions_router)
    application.include_router(verification_router)
    application.include_router(followups_router)
    application.include_router(skills_router)
    application.include_router(experience_router)
    application.include_router(knowledge_router)
    application.include_router(guard_router)
    return application


app = create_app()
