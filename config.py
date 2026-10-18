import os
import re
import ipaddress
from urllib.parse import urlsplit
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

def is_production(env=None) -> bool:
    """
    Returns True if the environment indicates a production deployment.
    Recognizes:
      - FLASK_ENV=production
      - ENV=production
      - RENDER=true or RENDER=1
    Consistently trims surrounding whitespace and handles case-insensitivity.
    """
    if env is None:
        env = os.environ

    flask_env = env.get('FLASK_ENV', '')
    flask_env = str(flask_env).strip().lower() if flask_env is not None else ''

    app_env = env.get('ENV', '')
    app_env = str(app_env).strip().lower() if app_env is not None else ''

    render = env.get('RENDER', '')
    render = str(render).strip().lower() if render is not None else ''

    return flask_env == 'production' or app_env == 'production' or render in ('true', '1')


_DOMAIN_LABEL_REGEX = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$', re.IGNORECASE)


def _is_valid_hostname(hostname: str) -> bool:
    """Validates domain name syntax (RFC 1123) or IPv4/IPv6 address."""
    if not hostname or len(hostname) > 253:
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    labels = hostname.split('.')
    return all(bool(_DOMAIN_LABEL_REGEX.match(label)) for label in labels)


def parse_allowed_origins(raw_origins, is_prod=False):
    """
    Parses and validates ALLOWED_ORIGINS.
    In production:
      - raw_origins must be set and non-empty.
      - Comma-separated entries are trimmed and filtered.
      - At least one valid origin must be present.
      - Wildcard '*' is strictly prohibited.
      - Embedded credentials (userinfo) are strictly prohibited.
      - Ports must be valid integers between 1 and 65535 without uncaught exceptions.
      - Hostnames must be valid RFC domain names, IPv4, or IPv6 literals.
      - Control characters and internal whitespace are strictly rejected.
      - No path (except an optional trailing slash), query string, or fragment is allowed.
      - Exception messages never leak credentials or sensitive tokens.
      - Valid origins are normalized to 'scheme://netloc'.
    In development:
      - If raw_origins is provided, parses comma-separated entries.
      - If not provided or empty, defaults to "*".
    """
    if is_prod:
        if not raw_origins or not str(raw_origins).strip():
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: The ALLOWED_ORIGINS environment variable must be set in production "
                "(e.g. 'https://your-service.onrender.com')!"
            )
        if any(ord(c) < 32 or ord(c) == 127 for c in str(raw_origins)):
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. Control characters are not permitted."
            )
        raw_list = [o.strip() for o in str(raw_origins).split(',') if o.strip()]
        if not raw_list:
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: The ALLOWED_ORIGINS environment variable must contain at least one valid origin in production!"
            )

        validated_origins = []
        for origin in raw_list:
            # 1. Wildcard check
            if origin == '*':
                raise RuntimeError(
                    "CRITICAL SECURITY ERROR: Wildcard '*' is not permitted for ALLOWED_ORIGINS in production!"
                )

            # 2. Control characters & whitespace check
            if any(ord(c) < 32 or ord(c) == 127 for c in origin):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. Control characters are not permitted."
                )
            if any(c.isspace() for c in origin):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. Whitespace within origin is not permitted."
                )

            # 3. Embedded credentials check BEFORE parsing or echoing in errors
            if '@' in origin:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Embedded credentials (userinfo) are strictly prohibited."
                )

            # 4. Parse URL components (safely catch any urllib syntax errors)
            try:
                parsed = urlsplit(origin)
            except ValueError:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Hostname is not a valid domain or IP address."
                )

            # Double-check userinfo from parsed object
            if parsed.username or parsed.password:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Embedded credentials (userinfo) are strictly prohibited."
                )

            # 5. Scheme check
            if parsed.scheme.lower() not in ('http', 'https'):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Scheme must be 'http' or 'https'."
                )

            # 6. Hostname and Netloc presence check
            if not parsed.netloc or not parsed.hostname:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Missing valid hostname."
                )

            # 7. Hostname validity check (reject malformed labels, invalid characters)
            if not _is_valid_hostname(parsed.hostname):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Hostname is not a valid domain or IP address."
                )

            # 8. Safe Port validation (never leak uncaught ValueError, reject empty port)
            if parsed.netloc.endswith(':'):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Port must be a valid integer between 1 and 65535."
                )
            try:
                port = parsed.port
            except ValueError:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Port must be a valid integer between 1 and 65535."
                )
            if port is not None and not (1 <= port <= 65535):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Port is out of valid range (1-65535)."
                )

            # 9. Path check (only empty or single trailing slash allowed)
            if parsed.path not in ('', '/'):
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Origin must not include a path."
                )

            # 10. Query parameters check (sensitive tokens not echoed)
            if parsed.query:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Origin must not include query parameters."
                )

            # 11. Fragment check (sensitive tokens not echoed)
            if parsed.fragment:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Invalid origin in ALLOWED_ORIGINS. "
                    "Origin must not include a fragment."
                )

            # 12. Canonical normalization
            normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if normalized not in validated_origins:
                validated_origins.append(normalized)

        return validated_origins
    else:
        if raw_origins and str(raw_origins).strip():
            origins = [o.strip() for o in str(raw_origins).split(',') if o.strip()]
            if len(origins) == 1 and origins[0] == '*':
                return "*"
            return origins if origins else "*"
        return "*"


class Config:
    # Production detection
    _is_prod = is_production()

    # Security: Require explicit SECRET_KEY in production, warn in development
    _raw_secret = os.environ.get('SECRET_KEY')
    if not _raw_secret or not _raw_secret.strip():
        if _is_prod:
            raise RuntimeError("CRITICAL SECURITY ERROR: The SECRET_KEY environment variable must be set in production!")
        SECRET_KEY = 'dev-insecure-key-set-SECRET_KEY-in-production'
    else:
        SECRET_KEY = _raw_secret.strip()

    basedir = os.path.abspath(os.path.dirname(__file__))
    _db_url = os.environ.get('DATABASE_URL')
    if _db_url:
        _db_url = _db_url.strip()
        if _db_url.startswith('postgres://'):
            _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

    if not _db_url and _is_prod:
        raise RuntimeError("CRITICAL CONFIGURATION ERROR: The DATABASE_URL environment variable must be set in production!")

    SQLALCHEMY_DATABASE_URI = _db_url or ('sqlite:///' + os.path.join(basedir, 'skillxchange.db'))
    
    # Allowed origins for Socket.IO and CORS
    CORS_ALLOWED_ORIGINS = parse_allowed_origins(os.environ.get('ALLOWED_ORIGINS'), is_prod=_is_prod)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # max 50 MB upload


    # Flask-Mail configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'your-email@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'your-app-password'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'your-email@gmail.com'

    # Flask-APScheduler configuration: Disable public management REST endpoints & enforce UTC
    SCHEDULER_API_ENABLED = False
    SCHEDULER_TIMEZONE = "UTC"


