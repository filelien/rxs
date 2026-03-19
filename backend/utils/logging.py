import logging
import sys
import structlog
from backend.config import get_settings


def setup_logging():
    settings = get_settings()
    log_level = logging.DEBUG if settings.app_debug else logging.INFO

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if not settings.is_production
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Silence noisy libs
    for lib in ("uvicorn.access", "motor", "pymongo"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str):
    return structlog.get_logger(name)
