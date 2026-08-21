"""WebCom configuration store.

Security model (per owner's requirements):
- All persisted state lives in the mounted /data volume ONLY.
- TeamTalk server credentials are stored PLAINTEXT. This is NOT our choice:
  TeamTalk's protocol requires plaintext passwords (bearware documents this and
  will not fix it). We store them in the volume, gitignored, never in the image/repo.
- The web dashboard admin login is argon2-hashed. We never store the raw web password.
- config.local.json is the WebCom-authoritative store. We also generate PowerCom's
  native ttcom.conf from it (PowerCom reads ttcom.conf at import time).

File layout in /data:
  config.local.json   - WebCom store (web admin argon2 hash + TT servers plaintext)
  ttcom.conf          - generated PowerCom config (consumed by TTComCmd)
"""
from __future__ import annotations

import json
import os
import secrets
import string
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("WEBCOM_DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "config.local.json"
TTCOM_CONF_PATH = DATA_DIR / "ttcom.conf"

DEFAULT_PORT = int(os.environ.get("WEBCOM_PORT", "2032"))
DEFAULT_BIND = os.environ.get("WEBCOM_BIND", "0.0.0.0")


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def is_configured() -> bool:
    """True if a valid config (with web admin) exists."""
    if not CONFIG_PATH.is_file():
        return False
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get("webcom", {}).get("admin_hash"))


# ---------------------------------------------------------------------------
# Web admin (argon2) - kept separate from TT creds
# ---------------------------------------------------------------------------
def hash_web_password(password: str) -> str:
    from argon2 import PasswordHasher
    return PasswordHasher().hash(password)


def verify_web_password(password: str, hashed: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
    try:
        PasswordHasher().verify(hashed, password)
        return True
    except (VerifyMismatchError, VerificationError, Exception):
        return False


def _gen_secret(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------
def load() -> dict:
    _ensure_dir()
    if not CONFIG_PATH.is_file():
        return {"webcom": {}, "servers": []}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"webcom": {}, "servers": []}


def save(data: dict) -> None:
    _ensure_dir()
    # Always ensure a session secret exists (used for cookie signing).
    wc = data.setdefault("webcom", {})
    wc.setdefault("session_secret", _gen_secret())
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Setup wizard writer
# ---------------------------------------------------------------------------
def setup_web_admin(username: str, password: str) -> None:
    """Create the web dashboard admin (argon2). Idempotent on first run."""
    data = load()
    data.setdefault("webcom", {})
    data["webcom"]["admin_user"] = username
    data["webcom"]["admin_hash"] = hash_web_password(password)
    data["webcom"].setdefault("session_secret", _gen_secret())
    save(data)


def add_server(server: dict) -> None:
    """Add or replace a TT server entry by shortname.

    server keys: shortname, host, tcpport, udpport, username, password,
    nickname, status, encrypted (bool), autoLogin (int), and optional
    notification toggles.
    """
    data = load()
    servers = data.setdefault("servers", [])
    shortname = server.get("shortname")
    for i, s in enumerate(servers):
        if s.get("shortname") == shortname:
            servers[i] = server
            break
    else:
        servers.append(server)
    save(data)


def list_servers() -> list[dict]:
    return load().get("servers", [])


def get_server(shortname: str) -> dict | None:
    for s in list_servers():
        if s.get("shortname") == shortname:
            return s
    return None


def delete_server(shortname: str) -> None:
    data = load()
    data["servers"] = [s for s in data.get("servers", []) if s.get("shortname") != shortname]
    save(data)


# ---------------------------------------------------------------------------
# PowerCom ttcom.conf generation (TT creds stay plaintext - TT's design)
# ---------------------------------------------------------------------------
_NOTIFY_KEYS = (
    "notifyloginout", "notifymessage", "systemnotify", "ntfy",
    "ntfyUrl", "ntfyTopic", "ntfyUser", "ntfyPassword",
    "prowl", "prowlkey", "mgnotify", "mgnotifykey",
    "pushover", "pushoveruser", "pushovertoken", "pushoverdevice",
    "pushoversound", "pushoverpriority", "pushoverretry", "pushoverexpire",
)


def generate_ttcom_conf() -> Path:
    """Write PowerCom's native ttcom.conf from our store.

    TT creds are written in plaintext (host, username, password, ports) because
    TeamTalk requires it. This file lives in the /data volume, gitignored.
    """
    _ensure_dir()
    data = load()
    lines: list[str] = [
        "; Auto-generated by WebCom. Do not edit by hand.",
        "; TeamTalk credentials are plaintext by TeamTalk's own design.",
        "",
        "[server defaults]",
        "autoLogin=0",
        "hidden=0",
        "silent=0",
        "speech=false",
        "sounds=false",
        "notifyLogInOut=true",
        "notifyMessage=true",
        "systemNotify=false",
        "ntfy=false",
        "prowl=false",
        "mgNotify=false",
        "pushover=false",
        "log=true",
        "maxLogSize=4",
        "maxLogFiles=5",
        "",
    ]
    for s in data.get("servers", []):
        sn = s.get("shortname", "server")
        lines.append(f"[server {sn}]")
        lines.append(f"host={s.get('host', '')}")
        lines.append(f"tcpport={s.get('tcpport', 10333)}")
        lines.append(f"udpport={s.get('udpport', 10333)}")
        lines.append(f"username={s.get('username', '')}")
        # PLAINTEXT by TT design - documented, unavoidable.
        lines.append(f"password={s.get('password', '')}")
        lines.append(f"nickname={s.get('nickname', 'WebCom')}")
        if s.get("status"):
            lines.append(f"statusmsg={s.get('status')}")
        lines.append(f"encrypted={'1' if s.get('encrypted') else '0'}")
        lines.append(f"autoLogin={s.get('autoLogin', 1)}")
        # Channel to auto-join after login (e.g. /text/). Stored as a passthrough
        # key; WebCom issues `join <channel>` post-login (PowerCom has no native
        # auto-join-on-login from config).
        if s.get("channel"):
            lines.append(f"channel={s.get('channel')}")
        # Notification toggles (optional, per-server)
        for k in _NOTIFY_KEYS:
            if k in s:
                lines.append(f"{k}={s[k]}")
        lines.append("")
    TTCOM_CONF_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Restrict permissions since this contains plaintext passwords
    try:
        TTCOM_CONF_PATH.chmod(0o600)
    except Exception:
        pass
    return TTCOM_CONF_PATH
