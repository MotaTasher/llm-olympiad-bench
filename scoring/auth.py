from __future__ import annotations

import re
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


@dataclass
class AuthUser(UserMixin):
    id: int
    username: str
    password_hash: str
    active: bool
    session_version: int
    created_at: str
    updated_at: str

    def get_id(self) -> str:
        return f"{self.id}:{self.session_version}"

    @property
    def is_active(self) -> bool:
        return self.active


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_username(username: str) -> str:
    return username.strip()


def validate_username(username: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("username must be 3-64 chars: latin letters, digits, '.', '_' or '-'")
    return normalized


def generated_password() -> str:
    return secrets.token_urlsafe(32)


def auth_db_path(app: Flask) -> Path:
    configured = app.config.get("AUTH_DB") or app.config.get("SCORER_AUTH_DB")
    if configured:
        return Path(configured)
    return Path(app.instance_path) / "scorer-auth.sqlite3"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def init_db(path: Path) -> None:
    with closing(connect(path)) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                session_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        if "session_version" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
        db.commit()


def _user_from_row(row: sqlite3.Row | None) -> AuthUser | None:
    if row is None:
        return None
    return AuthUser(
        id=int(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        active=bool(row["is_active"]),
        session_version=int(row["session_version"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def get_user_by_username(path: Path, username: str) -> AuthUser | None:
    init_db(path)
    normalized = normalize_username(username)
    with closing(connect(path)) as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    return _user_from_row(row)


def get_active_user_for_session(path: Path, session_user_id: str) -> AuthUser | None:
    init_db(path)
    try:
        raw_user_id, raw_session_version = session_user_id.split(":", 1)
        user_id = int(raw_user_id)
        session_version = int(raw_session_version)
    except (TypeError, ValueError):
        return None
    with closing(connect(path)) as db:
        row = db.execute(
            "SELECT * FROM users WHERE id = ? AND session_version = ? AND is_active = 1",
            (user_id, session_version),
        ).fetchone()
    return _user_from_row(row)


def authenticate_user(path: Path, username: str, password: str) -> AuthUser | None:
    user = get_user_by_username(path, username)
    if not user or not user.is_active:
        return None
    if not check_password_hash(user.password_hash, password):
        return None
    return user


def create_user(path: Path, username: str) -> tuple[AuthUser, str]:
    username = validate_username(username)
    password = generated_password()
    password_hash = generate_password_hash(password)
    now = utc_now()
    init_db(path)
    try:
        with closing(connect(path)) as db:
            cursor = db.execute(
                """
                INSERT INTO users (username, password_hash, is_active, session_version, created_at, updated_at)
                VALUES (?, ?, 1, 0, ?, ?)
                """,
                (username, password_hash, now, now),
            )
            db.commit()
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"user already exists: {username}") from exc
    user = get_user_by_id(path, user_id)
    if user is None:  # pragma: no cover - defensive against unexpected sqlite behavior
        raise RuntimeError("created user could not be loaded")
    return user, password


def get_user_by_id(path: Path, user_id: int) -> AuthUser | None:
    init_db(path)
    with closing(connect(path)) as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row)


def reset_password(path: Path, username: str) -> tuple[AuthUser, str]:
    username = normalize_username(username)
    password = generated_password()
    password_hash = generate_password_hash(password)
    now = utc_now()
    init_db(path)
    with closing(connect(path)) as db:
        cursor = db.execute(
            """
            UPDATE users
            SET password_hash = ?, session_version = session_version + 1, updated_at = ?
            WHERE username = ?
            """,
            (password_hash, now, username),
        )
        db.commit()
    if cursor.rowcount != 1:
        raise ValueError(f"user not found: {username}")
    user = get_user_by_username(path, username)
    if user is None:  # pragma: no cover
        raise RuntimeError("updated user could not be loaded")
    return user, password


def set_user_active(path: Path, username: str, active: bool) -> AuthUser:
    username = normalize_username(username)
    now = utc_now()
    init_db(path)
    with closing(connect(path)) as db:
        cursor = db.execute(
            """
            UPDATE users
            SET is_active = ?, session_version = session_version + 1, updated_at = ?
            WHERE username = ?
            """,
            (1 if active else 0, now, username),
        )
        db.commit()
    if cursor.rowcount != 1:
        raise ValueError(f"user not found: {username}")
    user = get_user_by_username(path, username)
    if user is None:  # pragma: no cover
        raise RuntimeError("updated user could not be loaded")
    return user


def list_users(path: Path) -> list[dict[str, Any]]:
    init_db(path)
    with closing(connect(path)) as db:
        rows = db.execute(
            "SELECT username, is_active, created_at, updated_at FROM users ORDER BY username COLLATE NOCASE"
        ).fetchall()
    return [
        {
            "username": str(row["username"]),
            "status": "active" if row["is_active"] else "disabled",
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]
