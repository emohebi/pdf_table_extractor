"""
Logging configuration for the PDF Table Extractor.

This module provides a consistent logging setup across the application.
Logs include timestamps, log levels, and module names for easy debugging.

Example:
    from src.utils.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("Processing started")
    logger.error("Something went wrong", exc_info=True)
"""

import logging
import sys
from typing import Optional


# Store configured loggers to avoid duplicate handlers
_loggers: dict[str, logging.Logger] = {}


def setup_logger(
    name: str = "pdf_extractor",
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Set up and configure a logger instance.
    
    Args:
        name: Logger name (usually __name__ of the calling module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
        format_string: Custom format string for log messages
    
    Returns:
        Configured Logger instance
    """
    # Return existing logger if already configured
    if name in _loggers:
        return _loggers[name]
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Default format
    if format_string is None:
        format_string = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    
    formatter = logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    # Cache the logger
    _loggers[name] = logger
    
    return logger


def get_logger(name: str = "pdf_extractor") -> logging.Logger:
    """
    Get a logger instance, creating one if it doesn't exist.
    
    This is the primary function to use throughout the application.
    
    Args:
        name: Logger name (usually __name__ of the calling module)
    
    Returns:
        Logger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("Processing page 1")
    """
    if name in _loggers:
        return _loggers[name]
    
    return setup_logger(name)


class LogContext:
    """
    Context manager for temporary log level changes.
    
    Example:
        logger = get_logger(__name__)
        
        with LogContext(logger, "DEBUG"):
            logger.debug("This will be logged")
        
        logger.debug("This won't be logged if level is INFO")
    """
    
    def __init__(self, logger: logging.Logger, level: str):
        self.logger = logger
        self.new_level = getattr(logging, level.upper(), logging.INFO)
        self.old_level = logger.level
    
    def __enter__(self):
        self.logger.setLevel(self.new_level)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.old_level)
        return False
