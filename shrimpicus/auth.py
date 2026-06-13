"""Authentication utilities for user management."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against its hash."""
    try:
        _ph.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def validate_username(username: str) -> str | None:
    """Validate username format. Returns error message if invalid, None if valid."""
    if not username:
        return "Username is required."
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(username) > 20:
        return "Username must be at most 20 characters."
    if not all(c.isalnum() or c in "_-" for c in username):
        return "Username can only contain letters, numbers, underscore, and dash."
    return None


def validate_password(password: str) -> str | None:
    """Validate password format. Returns error message if invalid, None if valid."""
    if not password:
        return "Password is required."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    return None
