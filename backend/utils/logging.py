import sys
from pathlib import Path

from loguru import logger

# The log file sits in the backend folder (one level above utils/)
LOG_FILE = Path(__file__).resolve().parent.parent / "app.log"

# Start clean: remove loguru's default output
logger.remove()

# Terminal: short lines. diagnose=False keeps variable values (like keys) out of error traces
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}",
    diagnose=False,
)

# File: every message with its date, and a new file when this one gets big
logger.add(
    LOG_FILE,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}",
    rotation="5 MB",
    encoding="utf-8",
    diagnose=False,
)

__all__ = ["logger"]
