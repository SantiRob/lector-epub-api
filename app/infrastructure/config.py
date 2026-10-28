import json
import os


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "[]")
    try:
        origins = json.loads(raw)
    except ValueError as exc:
        raise ValueError("CORS_ORIGINS must be a JSON array") from exc
    if not isinstance(origins, list) or any(not isinstance(x, str) for x in origins):
        raise ValueError("CORS_ORIGINS must be a JSON array of strings")
    return origins
