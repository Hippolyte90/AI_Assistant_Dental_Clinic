"""User accounts: hashed passwords, signed session cookies and attempt limits."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

COOKIE_NAME = "cuspia_session"
SESSION_SECONDS = 12 * 60 * 60
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200
MAX_NAME_LENGTH = 80
MAX_EMAIL_LENGTH = 254
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class AccountError(ValueError):
    """An account request that cannot be accepted; the message is shown to the user."""


class AccountExists(AccountError):
    """This email is already registered."""


class AccountLimitReached(AccountError):
    """No more accounts can be created."""


@dataclass(frozen=True)
class User:
    """A signed-up user."""

    id: str
    name: str
    email: str


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def hash_password(password: str) -> str:
    """Salted scrypt hash. The password itself is never stored."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_encode(salt)}${_encode(digest)}"


def verify_password(stored: str, password: str) -> bool:
    """Check a password against a stored hash in constant time."""
    try:
        _scheme, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(expected, actual)


# Checked when the email is unknown, so both cases take the same time.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def normalize_email(email: str) -> str:
    """Emails are compared in lower case."""
    return email.strip().lower()


class UserStore:
    """Accounts in one JSON file under storage/."""

    def __init__(self, path: Path, max_accounts: int) -> None:
        self.path = path
        self.max_accounts = max_accounts
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, users: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(users, stream, indent=1)
        os.replace(temp, self.path)

    @staticmethod
    def _user(row: dict) -> User:
        return User(id=row["id"], name=row["name"], email=row["email"])

    def create(self, name: str, email: str, password: str) -> User:
        """Validate and register a new account."""
        name = name.strip()
        email = normalize_email(email)
        if not name or len(name) > MAX_NAME_LENGTH:
            raise AccountError("Please enter your name.")
        if len(email) > MAX_EMAIL_LENGTH or not EMAIL_RE.match(email):
            raise AccountError("Please enter a valid email address.")
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise AccountError(f"Use a password of at least {MIN_PASSWORD_LENGTH} characters.")
        password_hash = hash_password(password)
        with self._lock:
            users = self._read()
            if email in users:
                raise AccountExists("An account with this email already exists.")
            if len(users) >= self.max_accounts:
                raise AccountLimitReached("New accounts are not available right now.")
            row = {
                "id": uuid.uuid4().hex,
                "name": name,
                "email": email,
                "password_hash": password_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            users[email] = row
            self._write(users)
        return self._user(row)

    def authenticate(self, email: str, password: str) -> User | None:
        """Return the user if the email and password match."""
        if len(password) > MAX_PASSWORD_LENGTH:
            return None
        with self._lock:
            row = self._read().get(normalize_email(email))
        stored = row["password_hash"] if row else _DUMMY_HASH
        if not verify_password(stored, password) or row is None:
            return None
        return self._user(row)

    def get(self, user_id: str) -> User | None:
        """Find a user by id."""
        with self._lock:
            users = self._read()
        row = next((row for row in users.values() if row["id"] == user_id), None)
        return self._user(row) if row else None


def load_secret(path: Path) -> bytes:
    """Read the cookie-signing key, creating it on first use."""
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    path.write_bytes(secret)
    return secret


def _signature(secret: bytes, payload: str) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def create_token(secret: bytes, user_id: str, now: float | None = None) -> str:
    """Create a signed session token."""
    expires = int((time.time() if now is None else now) + SESSION_SECONDS)
    payload = f"{user_id}.{expires}.{secrets.token_hex(8)}"
    return f"{payload}.{_signature(secret, payload)}"


def verify_token(secret: bytes, token: str | None, now: float | None = None) -> str | None:
    """Return the user id of a valid, unexpired token."""
    if not token:
        return None
    payload, _, signature = token.rpartition(".")
    if not payload or not hmac.compare_digest(signature, _signature(secret, payload)):
        return None
    parts = payload.split(".")
    if len(parts) != 3:
        return None
    try:
        expires = int(parts[1])
    except ValueError:
        return None
    return parts[0] if (time.time() if now is None else now) < expires else None


class AttemptLimiter:
    """Counts recent attempts per visitor."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allowed(self, client: str) -> bool:
        """False when this visitor has reached the limit."""
        now = time.monotonic()
        with self._lock:
            entries = self._attempts.get(client)
            if entries is None:
                return True
            while entries and now - entries[0] > self.window:
                entries.popleft()
            if not entries:
                del self._attempts[client]
                return True
            return len(entries) < self.limit

    def record(self, client: str) -> None:
        """Remember one attempt."""
        with self._lock:
            self._attempts.setdefault(client, deque()).append(time.monotonic())

    def reset(self, client: str) -> None:
        """Forget a visitor's attempts."""
        with self._lock:
            self._attempts.pop(client, None)
