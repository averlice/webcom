"""Web dashboard authentication (argon2) + signed session cookie.

The web admin login is COMPLETELY SEPARATE from TeamTalk credentials:
- Web login: argon2-hashed, stored in config.local.json (webcom.admin_hash).
- TT creds: plaintext in the volume (TeamTalk's design, see config_store.py).

We sign the session cookie with a secret stored in the config so cookies can't
be forged without the volume. No TT credential is ever used to log into the web UI.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from flask import Blueprint, request, redirect, url_for, session

from . import config_store

auth_bp = Blueprint("auth", __name__)

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _secret() -> str:
    data = config_store.load()
    return data.get("webcom", {}).get("session_secret", "")


def _sign(payload: str) -> str:
    return hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(username: str) -> str:
    body = json.dumps({"u": username, "t": int(time.time())})
    return f"{body}.{_sign(body)}"


def _valid_token(token: str) -> bool:
    if not token or "." not in token:
        return False
    body, sig = token.rsplit(".", 1)
    expected = _sign(body)
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        data = json.loads(body)
    except Exception:
        return False
    if int(time.time()) - int(data.get("t", 0)) > SESSION_MAX_AGE:
        return False
    return True


def is_authenticated() -> bool:
    return _valid_token(session.get("token", ""))


def login_user(username: str) -> None:
    session["token"] = _make_token(username)
    session.permanent = True


def logout_user() -> None:
    session.pop("token", None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    from flask import render_template_string
    # Fresh install: no admin user exists yet, so the login page is a dead end.
    # Send the user to the setup wizard instead.
    if not config_store.is_configured():
        return redirect(url_for("setup"))
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        data = config_store.load()
        wc = data.get("webcom", {})
        if user == wc.get("admin_user") and config_store.verify_web_password(pw, wc.get("admin_hash", "")):
            login_user(user)
            return redirect(url_for("index"))
        return render_template_string(
            "<!doctype html><meta charset=utf-8>"
            "<title>WebCom - Login</title>"
            "<p style='color:red'>Invalid credentials.</p>"
            "<form method=post>Username <input name=username><br>"
            "Password <input name=password type=password><br>"
            "<input type=submit value=Login></form>"
        )
    return render_template_string(
        "<!doctype html><meta charset=utf-8>"
        "<title>WebCom - Login</title>"
        "<form method=post>Username <input name=username><br>"
        "Password <input name=password type=password><br>"
        "<input type=submit value=Login></form>"
    )


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))
