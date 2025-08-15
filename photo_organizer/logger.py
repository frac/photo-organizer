"""Logging configuration for photo organizer"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(level: int = logging.INFO, log_file: Optional[Path] = None) -> logging.Logger:
    """Setup logger with console and optional file output"""

    logger = logging.getLogger('photo_organizer')
    logger.setLevel(level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Create formatters
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always debug to file
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger
