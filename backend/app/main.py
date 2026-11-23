"""FastAPI application."""

import logging
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth as auth_routes
from app.api import catalog as catalog_routes
from app.api import sessions as session_routes
from app.config import CATALOG_PATH, PRICE_LIST_PATH, ROOT_DIR, Settings, get_settings
from app.services.auth import AttemptLimiter, UserStore, load_secret
from app.services.catalog import load_catalog, parse_price_list, save_catalog
from app.services.llm import LLMClient, LLMError, OllamaClient
from app.services.rules import load_rules
from app.services.stt import STTError, Transcriber, WhisperTranscriber
from app.services.workflow import ASSISTANT_UNAVAILABLE, Workflow, WorkflowError
from app.store import PlanNotFound, SessionNotFound, Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
PUBLIC_API_PATHS = {
    "/api/auth/status",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
}
SESSION_PATH = re.compile(r"^/api/sessions/([^/]+)")
JOB_PATH = re.compile(r"^/api/jobs/([^/]+)")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error_code": code, "message": message})


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    """Build the app; tests inject a fake LLM and transcriber."""
    settings = settings or get_settings()
    if not CATALOG_PATH.exists():
        save_catalog(parse_price_list(PRICE_LIST_PATH), CATALOG_PATH)
    catalog = load_catalog()
    rules = load_rules()
    rules.check_references(catalog)

    # With accounts on, the app may be reachable from the internet: no public API docs.
    protected = settings.auth_required
    app = FastAPI(
        title="Cuspia",
        docs_url=None if protected else "/docs",
        redoc_url=None if protected else "/redoc",
        openapi_url=None if protected else "/openapi.json",
    )
    app.state.users = UserStore(settings.storage_path / "users.json", settings.max_accounts)
    app.state.auth_secret = load_secret(settings.storage_path / "auth_secret.key")
    app.state.login_limiter = AttemptLimiter(limit=5, window_seconds=15 * 60)
    app.state.register_limiter = AttemptLimiter(limit=10, window_seconds=60 * 60)

    @app.middleware("http")
    async def require_sign_in(request: Request, call_next):
        path = request.url.path
        needs_user = settings.auth_required and path.startswith("/api")
        if needs_user and path not in PUBLIC_API_PATHS:
            user = auth_routes.current_user(request)
            if user is None:
                return _error(401, "sign_in_required", "Please sign in.")
            request.state.user_id = user.id
            flow: Workflow = request.app.state.workflow
            # Another user's plan is reported as missing, so ids reveal nothing.
            session_match = SESSION_PATH.match(path)
            if session_match and not flow.store.owned_by(session_match[1], user.id):
                return _error(404, "session_not_found", "This session does not exist.")
            job_match = JOB_PATH.match(path)
            if job_match:
                job = flow.job(job_match[1])
                if job is None or job["owner_id"] != user.id:
                    return _error(404, "not_found", "This plan version or job does not exist.")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "microphone=(self)"
        if path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.workflow = Workflow(
        settings,
        catalog,
        rules,
        llm or OllamaClient(settings),
        transcriber or WhisperTranscriber(settings),
        Store(settings.storage_path),
    )

    @app.exception_handler(SessionNotFound)
    async def session_missing(_request: Request, _exc: SessionNotFound) -> JSONResponse:
        return _error(404, "session_not_found", "This session does not exist.")

    @app.exception_handler(PlanNotFound)
    async def plan_missing(_request: Request, _exc: PlanNotFound) -> JSONResponse:
        return _error(404, "not_found", "This plan version or job does not exist.")

    @app.exception_handler(WorkflowError)
    async def workflow_error(_request: Request, exc: WorkflowError) -> JSONResponse:
        return _error(409, "invalid_request", str(exc))

    @app.exception_handler(STTError)
    async def stt_error(_request: Request, exc: STTError) -> JSONResponse:
        return _error(422, "stt_failed", str(exc))

    @app.exception_handler(LLMError)
    async def llm_error(_request: Request, exc: LLMError) -> JSONResponse:
        logging.getLogger(__name__).error("Assistant engine error: %s", exc)
        return _error(503, "assistant_unavailable", ASSISTANT_UNAVAILABLE)

    @app.get("/api/health")
    def health(request: Request) -> dict:
        """Service status, including the local LLM."""
        flow: Workflow = request.app.state.workflow
        check = getattr(flow.llm, "health", None)
        return {
            "status": "ok",
            "llm": check() if check else "ok",
            "catalog_items": len(flow.catalog.items),
            "rules_validated": flow.rules.validated,
            "clinic_name": flow.settings.clinic_name,
        }

    app.include_router(auth_routes.router)
    app.include_router(catalog_routes.router)
    app.include_router(session_routes.router)
    if (FRONTEND_DIST / "index.html").exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
