"""FastAPI application."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import catalog as catalog_routes
from app.api import sessions as session_routes
from app.config import CATALOG_PATH, PRICE_LIST_PATH, Settings, get_settings
from app.services.catalog import load_catalog, parse_price_list, save_catalog
from app.services.llm import LLMClient, LLMError, OllamaClient
from app.services.rules import load_rules
from app.services.stt import STTError, Transcriber, WhisperTranscriber
from app.services.workflow import Workflow, WorkflowError
from app.store import PlanNotFound, SessionNotFound, Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


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

    app = FastAPI(title="Dental Treatment Plan Assistant")
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
        return _error(503, "llm_failed", str(exc))

    @app.get("/api/health")
    def health(request: Request) -> dict:
        """Service status, including the local LLM."""
        flow: Workflow = request.app.state.workflow
        check = getattr(flow.llm, "health", None)
        return {
            "status": "ok",
            "llm": check() if check else "ok",
            "model": flow.settings.llm_model,
            "catalog_items": len(flow.catalog.items),
            "rules_validated": flow.rules.validated,
            "clinic_name": flow.settings.clinic_name,
        }

    app.include_router(catalog_routes.router)
    app.include_router(session_routes.router)
    return app


app = create_app()
