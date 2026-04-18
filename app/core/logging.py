"""
Structured logging configuration using Loguru.

Call configure_logging() once at application startup (in main.py)
to set up consistent, level-aware logging across the entire project.
"""

import sys

from loguru import logger

from app.core.config import settings


def configure_logging() -> None:
    """Configure Loguru with appropriate sinks and format for the environment.

    In DEBUG mode, logs at DEBUG level with full context.
    In production, logs at INFO level with a more compact format.
    The stdlib logging module is also intercepted so third-party libraries
    (SQLAlchemy, uvicorn, etc.) route through Loguru.
    """
    import logging

    # Remove default Loguru sink
    logger.remove()

    log_level = "DEBUG" if settings.DEBUG else "INFO"
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Add stdout sink
    logger.add(
        sys.stdout,
        level=log_level,
        format=log_format,
        colorize=True,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
    )

    # Intercept stdlib logging (uvicorn, SQLAlchemy, etc.)
    class InterceptHandler(logging.Handler):
        """Routes stdlib log records into Loguru."""

        def emit(self, record: logging.LogRecord) -> None:
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno  # type: ignore[assignment]
            frame, depth = sys._getframe(6), 6
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back  # type: ignore[assignment]
                depth += 1
            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logger.info(
        "Logging configured | level={} | debug={}", log_level, settings.DEBUG
    )
