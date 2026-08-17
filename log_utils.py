"""
Logging Utilities
=================
Structured logging with rotating file handler, request tracking, and
security event logging (login attempts, errors, suspicious activity).

Log files are stored in the logs/ directory with automatic rotation:
    logs/app.log          — General application activity
    logs/security.log     — Auth events (logins, registrations, OTPs)
    logs/error.log        — 4xx/5xx responses and exceptions

Usage:
    from log_utils import get_logger, log_request, log_security_event

    logger = get_logger('my_module')
    logger.info('Processing prediction for %s', ticker)
    logger.error('Failed to fetch data: %s', err)

    # In a request handler:
    log_security_event('LOGIN_FAILED', email=email, ip=client_ip)
"""

import os
import logging
import logging.handlers
import time
from datetime import datetime
from functools import wraps

# ============================================================
# Configuration
# ============================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Ensure .gitkeep for logs directory
gitkeep = os.path.join(LOG_DIR, '.gitkeep')
if not os.path.exists(gitkeep):
    with open(gitkeep, 'w') as f:
        f.write('')

# Log format: timestamp | level | module | message
LOG_FORMAT = '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Sensitive fields to redact from log messages
SENSITIVE_FIELDS = ['password', 'confirm_password', 'password_hash',
                    'new_password', 'otp', 'token', 'api_key', 'secret',
                    'csrf_token', 'authorization', 'access_token',
                    'refresh_token', 'credit_card', 'ssn']


def _redact_sensitive_data(msg):
    """Redact sensitive field values from log messages."""
    msg_str = str(msg)
    for field in SENSITIVE_FIELDS:
        # Replace patterns like password=abc123 or "password": "abc123"
        import re
        # Query string / form data pattern
        msg_str = re.sub(
            rf'{re.escape(field)}=[^&\s]+',
            f'{field}=[REDACTED]',
            msg_str,
            flags=re.IGNORECASE
        )
        # JSON pattern
        msg_str = re.sub(
            rf'("{re.escape(field)}"\s*:\s*)"[^"]*"',
            rf'\1"[REDACTED]"',
            msg_str,
            flags=re.IGNORECASE
        )
    return msg_str


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts sensitive data from all log records."""

    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = _redact_sensitive_data(record.msg)
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                _redact_sensitive_data(a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


# ============================================================
# Logger Setup
# ============================================================

def _create_handler(filename, level=logging.INFO, max_bytes=5*1024*1024,
                    backup_count=10):
    """Create a rotating file handler."""
    path = os.path.join(LOG_DIR, filename)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count,
        encoding='utf-8'
    )
    handler.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())
    return handler


def _create_console_handler(level=logging.INFO):
    """Create a console handler for development."""
    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter(
        '[%(levelname)s] %(name)s | %(message)s'
    )
    handler.setFormatter(formatter)
    return handler


def setup_logging():
    """
    Configure the root logger with rotating file handlers.

    Returns the root logger.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on re-import
    if root_logger.handlers:
        return root_logger

    # Application log (INFO and above)
    root_logger.addHandler(_create_handler('app.log', logging.INFO))

    # Error log (WARNING and above)
    root_logger.addHandler(_create_handler('error.log', logging.WARNING))

    # Console output for development
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    if debug:
        root_logger.addHandler(_create_console_handler(logging.DEBUG))

    # Suppress noisy library loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)

    root_logger.info('=' * 55)
    root_logger.info('Logging initialized')
    root_logger.info('=' * 55)

    return root_logger


def get_logger(name):
    """
    Get a logger for a specific module.

    Args:
        name: Usually __name__ of the calling module.

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(name)


# ============================================================
# Security Event Logger
# ============================================================

_security_logger = None


def _get_security_logger():
    """
    Get or create the security-specific logger.
    Writes to logs/security.log with INFO level.
    """
    global _security_logger
    if _security_logger is None:
        _security_logger = logging.getLogger('security')
        _security_logger.setLevel(logging.INFO)
        _security_logger.propagate = False  # Don't duplicate to root
        _security_logger.addHandler(
            _create_handler('security.log', logging.INFO)
        )
    return _security_logger


def log_security_event(event_type, **context):
    """
    Log a security-relevant event.

    Args:
        event_type: Short event name like 'LOGIN_FAILED', 'REGISTER',
                   'OTP_REQUEST', 'RATE_LIMITED'
        **context: Key-value pairs to include (email, ip, reason, etc.)

    Example:
        log_security_event('LOGIN_FAILED', email='a@b.com', ip='192.168.1.1')
    """
    logger = _get_security_logger()
    context_str = ' | '.join(
        f"{k}={v}" for k, v in context.items() if v is not None
    )
    logger.info('%s | %s', event_type, context_str)


# ============================================================
# Flask Request Logging Middleware
# ============================================================

def log_request_middleware(app):
    """
    Add request logging to a Flask application.

    Logs every request with method, path, status, duration, and IP.
    Also logs rate-limited requests and 4xx/5xx responses to error.log.

    Usage:
        from log_utils import log_request_middleware
        log_request_middleware(app)
    """
    logger = get_logger('http')

    @app.before_request
    def start_timer():
        """Record the start time of each request."""
        from flask import request
        request._start_time = time.time()

    @app.after_request
    def log_request(response):
        """Log every request after it completes."""
        from flask import request

        # Skip static file requests to reduce noise
        if request.path.startswith('/static/'):
            return response

        duration = time.time() - getattr(request, '_start_time', time.time())
        status_code = response.status_code
        method = request.method
        path = request.path
        ip = request.remote_addr or 'unknown'
        user_agent = request.headers.get('User-Agent', '')[:80]

        # Determine log level based on status code
        if status_code >= 500:
            logger.error(
                '%s %s -> %s (%dms) [%s]',
                method, path, status_code, int(duration * 1000), ip
            )
        elif status_code >= 400:
            logger.warning(
                '%s %s -> %s (%dms) [%s]',
                method, path, status_code, int(duration * 1000), ip
            )
        else:
            logger.info(
                '%s %s -> %s (%dms) [%s]',
                method, path, status_code, int(duration * 1000), ip
            )

        return response

    @app.errorhandler(404)
    def not_found_error(e):
        """Log 404 errors."""
        from flask import request
        logger.warning('404 %s [%s]', request.path, request.remote_addr)
        return e

    @app.errorhandler(500)
    def internal_error(e):
        """Log 500 errors."""
        from flask import request
        logger.exception(
            '500 %s [%s]', request.path, request.remote_addr
        )
        return e


# ============================================================
# Initialize on import
# ============================================================

setup_logging()
