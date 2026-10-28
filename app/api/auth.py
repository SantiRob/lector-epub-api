import os
import secrets
import base64
import binascii
import hashlib

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)


def valid_admin_pair(username: str, password: str) -> bool:
    expected_user = os.getenv("ADMIN_USERNAME")
    expected_password = os.getenv("ADMIN_PASSWORD")
    if not expected_user or not expected_password:
        return False
    # Hash first so comparison length and both comparisons are fixed.
    user_ok = secrets.compare_digest(hashlib.sha256(username.encode()).digest(), hashlib.sha256(expected_user.encode()).digest())
    password_ok = secrets.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(expected_password.encode()).digest())
    return user_ok & password_ok


def valid_basic_header(value: bytes | None) -> bool:
    if not value or not value.lower().startswith(b"basic "):
        return False
    try:
        raw = base64.b64decode(value[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    username, separator, password = raw.partition(":")
    return bool(separator) and valid_admin_pair(username, password)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    valid = bool(credentials and valid_admin_pair(credentials.username, credentials.password))
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
