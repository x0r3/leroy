"""Local administrative account operations; passwords never appear in command arguments."""

from pwdlib import PasswordHash
from sqlalchemy import delete, func, select, text

from .db import Session, User
from .engine import event


def manage_account(sessions, action, name, *, role=None, password=None):
    if not name or len(name) > 100 or any(ord(c) < 32 for c in name):
        raise ValueError("Invalid account name")
    if role is not None and role not in ("admin", "operator", "viewer"):
        raise ValueError("Unknown role")
    if action not in ("add", "password", "role", "delete"):
        raise ValueError("Unknown account operation")
    if action in ("add", "password") and (password is None or not 16 <= len(password) <= 1024):
        raise ValueError("Passwords must contain 16 to 1024 characters")
    if action == "role" and role is None:
        raise ValueError("Specify a role")
    password_hash = PasswordHash.recommended().hash(password) if password is not None else None
    with sessions.begin() as db:
        # Login uses this lock too: no session can be created using a revoked password.
        db.execute(text("SELECT pg_advisory_xact_lock(7046102)"))
        account = db.get(User, name)
        if action == "add":
            if account:
                raise ValueError("Account already exists")
            account = User(name=name, role=role or "viewer", password_hash=password_hash)
            db.add(account)
        else:
            if account is None:
                raise ValueError("Account does not exist")
            if name == "admin" and action == "delete":
                raise ValueError("The bootstrap administrator cannot be deleted; rotate its password instead")
            if account.role == "admin" and (action == "delete" or action == "role" and role != "admin"):
                count = db.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
                if count <= 1:
                    raise ValueError("Cannot remove the last administrator")
            db.execute(delete(Session).where(Session.user == name))
            if action == "password":
                account.password_hash = password_hash
            elif action == "role":
                account.role = role
            elif action == "delete":
                db.delete(account)
        event(db, None, "account." + action, {"account": name, "role": role, "actor": "local administrator"})
