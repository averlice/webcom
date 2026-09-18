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

_APP_DIR_ENV = os.environ.get("WEBCOM_APP_DIR", "")
APP_DIR = Path(_APP_DIR_ENV) if _APP_DIR_ENV else Path(__file__).resolve().parent.parent

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
def _strip_legacy(data: dict) -> dict:
    """Self-heal: drop the removed 'hidden' / 'excludeUsers' keys so every
    server shows up in every view and roster again."""
    for srv in data.get("servers", []):
        srv.pop("hidden", None)
        srv.pop("excludeUsers", None)
    return data


def load() -> dict:
    _ensure_dir()
    if not CONFIG_PATH.is_file():
        return {"webcom": {}, "servers": []}
    try:
        return _strip_legacy(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        return {"webcom": {}, "servers": []}


def save(data: dict) -> None:
    _ensure_dir()
    # Always ensure a session secret exists (used for cookie signing).
    wc = data.setdefault("webcom", {})
    wc.setdefault("session_secret", _gen_secret())
    _strip_legacy(data)
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
    shortname = str(server.get("shortname", "")).strip()
    if not shortname or any(char.isspace() for char in shortname):
        raise ValueError("Server short name is required and cannot contain spaces")
    server = dict(server)
    server["shortname"] = shortname
    for i, s in enumerate(servers):
        if s.get("shortname") == shortname:
            servers[i] = server
            break
    else:
        servers.append(server)
    save(data)


def list_servers() -> list[dict]:
    return load().get("servers", [])


def visible_servers() -> list[dict]:
    """All configured servers are shown in every WebCom view. The legacy
    'hidden' flag was removed from WebCom; kept as an identity alias."""
    return list_servers()


def get_server(shortname: str) -> dict | None:
    for s in list_servers():
        if s.get("shortname") == shortname:
            return s
    return None


def delete_server(shortname: str) -> None:
    data = load()
    data["servers"] = [s for s in data.get("servers", []) if s.get("shortname") != shortname]
    save(data)


def rename_server(old_sn: str, new_sn: str) -> None:
    """Rename a server entry in place, preserving every field.

    Raises ValueError when the old server is missing or the new short name is
    empty/invalid/already taken.
    """
    new_sn = str(new_sn or "").strip()
    if not new_sn or any(char.isspace() for char in new_sn):
        raise ValueError("Server short name is required and cannot contain spaces")
    data = load()
    servers = data.setdefault("servers", [])
    old = next((s for s in servers if s.get("shortname") == old_sn), None)
    if old is None:
        raise ValueError(f"Server {old_sn!r} not found")
    if new_sn == old_sn:
        return
    if any(s.get("shortname") == new_sn for s in servers):
        raise ValueError(f"Server {new_sn!r} already exists")
    old["shortname"] = new_sn
    save(data)


# ---------------------------------------------------------------------------
# Global notification defaults (per-server values override these)
# ---------------------------------------------------------------------------
def get_notify_defaults() -> dict:
    """Global per-server notification defaults (webcom.notif_defaults)."""
    return dict(load().get("webcom", {}).get("notif_defaults") or {})


def save_notify_defaults(settings: dict) -> None:
    """Persist global notification defaults, keeping only known keys."""
    data = load()
    wc = data.setdefault("webcom", {})
    wc["notif_defaults"] = {k: settings[k] for k in _NOTIFY_KEYS if k in settings}
    save(data)


def effective_notify_settings(server: dict, defaults: dict | None = None) -> dict:
    """Effective notification settings for a server.

    By default every server inherits global notification defaults.  When
    ``inheritNotifyDefaults`` is ``False`` the server's own stored keys
    take precedence, giving a clean way to override specific settings per
    server without duplicating the full set.
    """
    if defaults is None:
        defaults = get_notify_defaults()
    eff = {k: v for k, v in defaults.items() if k in _NOTIFY_KEYS}
    if not server.get("inheritNotifyDefaults", True):
        for k in _NOTIFY_KEYS:
            if k in server:
                eff[k] = server[k]
    return eff


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
        sn = str(s.get("shortname", "")).strip()
        # Do not emit a malformed [server ] section if an older WebCom version
        # saved one. The UI will surface it for correction instead.
        if not sn or any(char.isspace() for char in sn):
            continue
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
        # TTCom uses an exact channel-path comparison after login.  Normalize
        # the dashboard-friendly /text form to its canonical /text/ form so
        # it can match the channel list received from the server.
        if s.get("channel"):
            channel = str(s["channel"]).strip()
            if channel != "/":
                channel = "/" + channel.strip("/") + "/"
            lines.append(f"channel={channel}")
        # Notification toggles (global defaults, overridden per-server).
        eff = effective_notify_settings(s)
        for k in _NOTIFY_KEYS:
            if k in eff:
                lines.append(f"{k}={eff[k]}")
        lines.append("")
    TTCOM_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(TTCOM_CONF_PATH, "\n".join(lines) + "\n")
    # Restrict permissions since this contains plaintext passwords
    try:
        TTCOM_CONF_PATH.chmod(0o600)
    except Exception:
        pass
    try:
        app_conf = APP_DIR / "ttcom.conf"
        if app_conf.resolve() != TTCOM_CONF_PATH.resolve():
            _atomic_write_text(app_conf, "\n".join(lines) + "\n")
    except Exception:
        pass
    return TTCOM_CONF_PATH


def _atomic_write_text(path: Path, text: str) -> None:
    """Write a file atomically (temp file + rename) so file watchers never
    observe a partial/empty file. PowerCom reloads on every modification;
    mid-write reads previously crashed its config reload (conf.py __read)."""
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
