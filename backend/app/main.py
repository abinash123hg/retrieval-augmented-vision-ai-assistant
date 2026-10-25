"""DocuLens application entrypoint.

The shared error types and logging setup are defined FIRST, because the service
modules import the errors from here; defining them before ``from . import routes``
avoids a circular-import problem. The FastAPI app then wires the API routes under
/api and serves the static single-page UI (plain HTML/CSS/JS) at /.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings


# ---------------------------------------------------------------------------
# Application error types.
#
# Each error carries a user-friendly message; technical detail goes to logs only.
# ---------------------------------------------------------------------------
class AppError(Exception):
    status_code = 500
    user_message = "An unexpected error occurred. Please try again."

    def __init__(self, message: str | None = None, detail: str | None = None):
        self.user_message = message or self.user_message
        self.detail = detail
        super().__init__(self.user_message)


class InvalidFileError(AppError):
    status_code = 400
    user_message = "This file cannot be used. Please upload a valid PDF, PNG or JPG file."


class FileTooLargeError(AppError):
    status_code = 413
    user_message = "This file is larger than the allowed maximum size."


class DocumentNotFoundError(AppError):
    status_code = 404
    user_message = "This document is no longer available. It may have been removed."


class OllamaUnavailableError(AppError):
    status_code = 503
    user_message = (
        "Ollama is not running locally. Please start it with `ollama serve` and try again."
    )


class OllamaModelMissingError(AppError):
    status_code = 503
    user_message = (
        "Required Ollama model is not available. Please check the local Ollama model list."
    )


# ---------------------------------------------------------------------------
# Logging setup.
# ---------------------------------------------------------------------------
_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


setup_logging()
logger = logging.getLogger(__name__)

# Imported only after the error types and logging above are defined, so these
# modules can safely do ``from .main import <ErrorClass>``.
from . import pdf_service, routes  # noqa: E402

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A previous run may have crashed mid-pipeline; mark those documents failed
    # so the UI stops polling a state that will never resolve.
    pdf_service.recover_interrupted_documents()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Local document reading and question-answering with grounded answers.",
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    if exc.detail:
        logger.error("%s (%s) on %s: %s", type(exc).__name__, exc.user_message, request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.user_message})


# API routes are registered BEFORE the static mount so /api/* always wins.
app.include_router(routes.router, prefix="/api")

# Serve the single-page UI (plain HTML/CSS/JS) from the backend at /.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
