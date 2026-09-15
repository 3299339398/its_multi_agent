import json
from urllib.parse import urlsplit, urlunsplit


def normalize_model_base_url(value: str) -> str:
    if not isinstance(value, str) or not value or any(ord(char) <= 32 for char in value):
        raise ValueError("Invalid model base URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid model base URL") from None
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or "\\" in value
            or "%" in parsed.netloc or "%" in parsed.path
            or any(segment in (".", "..") for segment in parsed.path.split("/"))):
        raise ValueError("Invalid model base URL")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None and port != (443 if parsed.scheme == "https" else 80):
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def validate_model_base_url(value: str, config=None) -> str:
    if config is None:
        from its_multi_agent.backend.app.config.settings import settings
        config = settings
    allowed = json.loads(getattr(config, "MODEL_ALLOWED_BASE_URLS_JSON", "[]") or "[]")
    if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
        raise ValueError("MODEL_ALLOWED_BASE_URLS_JSON must be a JSON list of URLs")
    endpoints = list(allowed)
    profiles = json.loads(getattr(config, "MODEL_PROFILES_JSON", "") or "[]")
    endpoints.extend(profile["base_url"] for profile in profiles)
    for name in ("SF_BASE_URL", "AL_BAILIAN_BASE_URL", "DASHSCOPE_BASE_URL"):
        if endpoint := getattr(config, name, None):
            endpoints.append(endpoint)
    normalized = normalize_model_base_url(value)
    if normalized not in {normalize_model_base_url(endpoint) for endpoint in endpoints}:
        raise ValueError("Model base URL is not approved by the administrator")
    return normalized
