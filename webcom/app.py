"""WebCom Flask application.

Routes:
  /setup            First-run wizard (web admin + TT servers + notifications).
  /login /logout    argon2 web dashboard auth.
  /                 Dashboard (live event stream via SSE + channel chat + status).
  /servers          Manage multiple TT hosts (add/edit/remove/connect/disconnect).
  /notifications    Toggle ntfy/prowl/mgnotify/pushover/system per server.
  /pmsg             Compose & read private messages (standard TT or TTCom PM).
  /admin            Run administrative commands & quick actions.
  /logs             Real-time application logs in browser.
  /api/health       Health check.
  /api/debug/bridge Bridge readiness check.
  /api/servers/status Live server connection statuses.
  /api/chat         POST a message to the active channel on a server.
  /api/command      POST a TTCom command; returns captured output.
  /api/events       SSE stream of live TTCom events.
  /api/logs         Recent application logs.

Security: routes except /setup, /login, /api/health, /api/debug/bridge require argon2 authentication.
WebCom binds to 0.0.0.0:2032 by default; override via environment variables.
"""
from __future__ import annotations

import json
import time

from flask import (
    Flask, Blueprint, request, redirect, url_for, render_template_string,
    Response, session,
)

from . import config_store, auth
from . import notification_store
from .tt_bridge import bridge

app = Flask(__name__)
app.secret_key = "webcom-insecure-dev"  # replaced at runtime by session_secret
app.register_blueprint(auth.auth_bp)


def _validated_server(data: dict) -> dict:
    """Normalize connection fields before they reach ttcom.conf.

    PowerCom requires a non-empty, single-word server short name.
    """
    server = dict(data)
    shortname = str(server.get("shortname", "")).strip()
    host = str(server.get("host", "")).strip()
    if not shortname or any(char.isspace() for char in shortname):
        raise ValueError("Server short name is required and cannot contain spaces")
    if not host:
        raise ValueError("Server host is required")
    try:
        for key in ("tcpport", "udpport"):
            port = int(server.get(key) or 10333)
            if not 1 <= port <= 65535:
                raise ValueError
            server[key] = port
    except (TypeError, ValueError):
        raise ValueError("TCP and UDP ports must be between 1 and 65535") from None
    server["shortname"] = shortname
    server["host"] = host
    connect_on_start = server.get("connectOnStart", True)
    server["connectOnStart"] = (
        connect_on_start if isinstance(connect_on_start, bool)
        else str(connect_on_start).strip().lower() in {"1", "true", "yes", "on"}
    )
    return server


def _auth_guard():
    """Guard for web HTML pages: redirects to login if unauthenticated."""
    if not auth.is_authenticated():
        return redirect(url_for("auth.login"))
    return None


def _api_auth_guard():
    """Guard for API endpoints: returns JSON 401 if unauthenticated."""
    if not auth.is_authenticated():
        return {"ok": False, "error": "Authentication required"}, 401
    return None


@app.route("/")
def index():
    if not config_store.is_configured():
        return redirect(url_for("setup"))
    guard = _auth_guard()
    if guard:
        return guard
    from .pages import dashboard_html
    bridge.start()
    servers = config_store.list_servers()
    servers_status = bridge.get_servers_status()
    return render_template_string(dashboard_html(servers, servers_status))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if config_store.is_configured():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        user = request.form.get("web_user", "admin").strip()
        pw = request.form.get("web_pass", "")
        if not user:
            return "Username required", 400
        if not pw:
            return "Password required", 400
        config_store.setup_web_admin(user, pw)
        try:
            servers = json.loads(request.form.get("servers_json", "[]"))
        except json.JSONDecodeError:
            return "Invalid servers JSON", 400
        if not isinstance(servers, list) or not servers:
            return "At least one server required", 400
        for s in servers:
            if not isinstance(s, dict):
                continue
            try:
                s = _validated_server(s)
            except ValueError as exc:
                return str(exc), 400
            config_store.add_server(s)
        config_store.generate_ttcom_conf()
        try:
            bridge.connect_all()
        except Exception as e:
            import logging
            logging.getLogger("webcom").warning("connect_all failed during setup: %s", e)
        return redirect(url_for("auth.login"))
    from .pages import setup_html
    return render_template_string(setup_html())


@app.route("/servers/edit/<shortname>")
def edit_server(shortname):
    guard = _api_auth_guard()
    if guard:
        return guard
    s = config_store.get_server(shortname)
    if not s:
        return {"ok": False, "error": "Server not found"}, 404
    return {"ok": True, "server": s}


@app.route("/servers", methods=["GET", "POST", "DELETE"])
def servers():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        if not request.is_json:
            data["connectOnStart"] = "connectOnStart" in request.form
        try:
            data = _validated_server(data)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}, 400
        config_store.add_server(data)
        config_store.generate_ttcom_conf()
        bridge.refresh_and_connect()
        return {"ok": True}
    if request.method == "DELETE":
        sn = (request.get_json(silent=True) or {}).get("shortname")
        if sn:
            config_store.delete_server(sn)
            config_store.generate_ttcom_conf()
            bridge.refresh_and_connect()
        return {"ok": True}
    from .pages import servers_html
    servers_list = config_store.list_servers()
    servers_status = bridge.get_servers_status() if bridge._ready else []
    return render_template_string(servers_html(servers_list, servers_status))


@app.route("/servers/connect/<shortname>", methods=["POST"])
def connect_server_route(shortname):
    guard = _api_auth_guard()
    if guard:
        return guard
    bridge.connect_server(shortname)
    return {"ok": True, "message": f"Connecting to {shortname}..."}


@app.route("/servers/disconnect/<shortname>", methods=["POST"])
def disconnect_server_route(shortname):
    guard = _api_auth_guard()
    if guard:
        return guard
    bridge.disconnect_server(shortname)
    return {"ok": True, "message": f"Disconnected from {shortname}."}


_NOTIFY_FIELDS = (
    "notifyloginout", "notifymessage", "systemnotify",
    "ntfy", "prowl", "mgnotify", "pushover",
    "ntfyUrl", "ntfyTopic", "ntfyUser", "ntfyPassword",
    "prowlkey", "mgnotifykey", "pushoveruser", "pushovertoken",
)


def _apply_notification_settings(data: dict, from_form: bool = False) -> None:
    """Persist per-server notification settings from a settings POST."""
    if from_form:
        for key in ("notifyloginout", "notifymessage", "systemnotify",
                    "ntfy", "prowl", "mgnotify", "pushover"):
            data[key] = "1" if key in data else "0"
    sn = data.get("shortname")
    s = config_store.get_server(sn)
    if s:
        for k in _NOTIFY_FIELDS:
            if k in data:
                s[k] = data[k]
        config_store.add_server(s)
        config_store.generate_ttcom_conf()


# -- Admin user resolution (PowerCom-style numbered selection) ---------------
# Commands that take a user by name as an argument. When the typed name matches
# more than one user, WebCom asks the browser to pick from a numbered list
# (mirroring PowerCom's interactive 1/2/3 picker) instead of failing headlessly.
_USER_CMD_SPEC = {}


def _split_command(cmd: str) -> list[str] | None:
    import shlex
    try:
        return shlex.split(cmd)
    except Exception:
        return None


def _looks_like_ip(token: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(token)
        return True
    except ValueError:
        return False


def _admin_user_token(parts: list[str], spec: str) -> tuple[int | None, str | None]:
    """Return (index, token) of the user token, or (None, None) if none applies."""
    if spec == "first":
        idx = 1
        while idx < len(parts) and parts[idx].startswith("-"):
            idx += 1
        return (idx, parts[idx]) if idx < len(parts) else (None, None)
    if spec == "geolocate":
        idx = 1
        while idx < len(parts) and parts[idx].startswith("-"):
            idx += 1
        if idx >= len(parts):
            return (None, None)
        tok = parts[idx]
        if _looks_like_ip(tok):
            return (None, None)
        return (idx, tok)
    if spec == "move":
        # move <user> [<user> ...] <channel>; resolve the user tokens.
        if len(parts) < 3:
            return (None, None)
        for idx in range(1, len(parts) - 1):
            tok = parts[idx]
            if not tok.startswith("@") and not _looks_like_ip(tok):
                return (idx, tok)
        return (None, None)
    return (None, None)


def _run_admin_command(sn: str, cmd: str,
                       replace_index: int | None = None,
                       userid: str | None = None) -> dict:
    """Run an admin command, resolving user arguments to exact #userids.

    If a user-taking command's name matches more than one user, returns
    {needs_selection: True, matches: [...], command, user_index} so the UI can
    present a numbered picker. Single matches are silently rewritten to
    "#<userid>". Non-user commands run unchanged.
    """
    if replace_index is not None and userid:
        parts = _split_command(cmd)
        if parts and 0 <= replace_index < len(parts):
            parts[replace_index] = f"#{userid}"
            cmd = " ".join(parts)
    parts = _split_command(cmd)
    if parts:
        spec = _USER_CMD_SPEC.get(parts[0].lower())
        if spec:
            idx, token = _admin_user_token(parts, spec)
            if token is not None and not token.startswith("#"):
                matches = bridge.find_users(sn, token)
                if len(matches) > 1:
                    return {
                        "ok": True,
                        "needs_selection": True,
                        "command": cmd,
                        "user_index": idx,
                        "token": token,
                        "matches": matches,
                    }
                if len(matches) == 1:
                    parts[idx] = f"#{matches[0]['userid']}"
                    cmd = " ".join(parts)
    return {"ok": True, "output": bridge.run_command(sn, cmd)}


for _word in ("kick", "ckick", "kb", "subscribe", "address", "whois",
              "umsg", "pmsg"):
    _USER_CMD_SPEC[_word] = "first"
_USER_CMD_SPEC["op"] = "first"
_USER_CMD_SPEC["geolocate"] = "geolocate"
_USER_CMD_SPEC["move"] = "move"


@app.route("/notifications")
def notifications():
    guard = _auth_guard()
    if guard:
        return guard
    bridge.start()
    from .pages import notifications_html
    return render_template_string(notifications_html(config_store.list_servers()))


@app.route("/users")
def users_page():
    guard = _auth_guard()
    if guard:
        return guard
    bridge.start()
    from .pages import users_html
    return render_template_string(users_html(config_store.list_servers()))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        _apply_notification_settings(data, from_form=not request.is_json)
        return {"ok": True}
    from .pages import settings_html
    return render_template_string(settings_html(config_store.list_servers()))


@app.route("/pmsg", methods=["GET", "POST"])
def pmsg():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        sn = data.get("shortname", "")
        target = data.get("target", "")
        text = data.get("text", "")
        is_ttcom = str(data.get("is_ttcom", "false")).lower() in ("true", "1", "yes")
        out = bridge.send_pm(sn, target, text, is_ttcom=is_ttcom)
        return {"ok": True, "output": out}
    from .pages import pmsg_html
    return render_template_string(pmsg_html(config_store.list_servers()))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        sn = data.get("shortname", "")
        cmd = data.get("command", "")
        result = _run_admin_command(sn, cmd, data.get("replace_index"),
                                    data.get("userid"))
        if result.get("needs_selection"):
            return result
        return {"ok": True, "output": result.get("output", [])}
    from .pages import admin_html
    return render_template_string(admin_html(config_store.list_servers()))


@app.route("/logs")
def logs():
    guard = _auth_guard()
    if guard:
        return guard
    bridge.start()
    from .pages import logs_html
    return render_template_string(logs_html())


@app.route("/api/logs")
def api_logs():
    guard = _api_auth_guard()
    if guard:
        return guard
    bridge.start()
    logs = bridge.logs.get_recent(200)
    formatted = []
    import datetime
    for entry in logs:
        ts = datetime.datetime.fromtimestamp(entry["timestamp"]).strftime("%H:%M:%S")
        formatted.append(f"{ts} [{entry['level']}] {entry['source']}: {entry['message']}")
    return {"logs": "\n".join(formatted) or "No logs captured yet"}


@app.route("/api/health")
@app.route("/api/debug/bridge")
def api_debug_bridge():
    """Health check and debug endpoint."""
    return {
        "status": "ok",
        "ready": bridge._ready,
        "cmd_exists": bridge._cmd is not None,
        "log_count": len(bridge.logs.get_recent(1000)),
    }


@app.route("/api/servers/status")
def api_servers_status():
    guard = _api_auth_guard()
    if guard:
        return guard
    return {"ok": True, "servers": bridge.get_servers_status()}


@app.route("/api/users", methods=["POST"])
def api_users():
    guard = _api_auth_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or request.form.to_dict()
    sn = data.get("shortname", "")
    target = data.get("target", "")
    users = bridge.find_users(sn, target)
    return {"ok": True, "users": users}


@app.route("/api/users/roster")
def api_users_roster():
    guard = _api_auth_guard()
    if guard:
        return guard
    servers = config_store.list_servers()
    sn = request.args.get("server") or None
    if sn:
        roster = bridge.roster(sn)
        return {"ok": True, "roster": roster}
    out = []
    for s in servers:
        out.append(bridge.roster(s.get("shortname", "")))
    return {"ok": True, "rosters": out}


@app.route("/api/notifications")
def api_notifications():
    guard = _api_auth_guard()
    if guard:
        return guard
    server = request.args.get("server") or None
    kind = request.args.get("kind") or None
    direction = request.args.get("direction") or None
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    notifs = notification_store.query(server=server, kind=kind,
                                      direction=direction, limit=limit)
    return {"ok": True, "notifications": notifs,
            "unread": notification_store.unread_count(server)}


@app.route("/api/notifications/unread")
def api_notifications_unread():
    guard = _api_auth_guard()
    if guard:
        return guard
    server = request.args.get("server") or None
    return {"count": notification_store.unread_count(server)}


@app.route("/api/notifications/mark-read", methods=["POST"])
def api_notifications_mark_read():
    guard = _api_auth_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or request.form.to_dict()
    ids = data.get("ids")
    server = data.get("server") or None
    count = notification_store.mark_seen(ids=ids, server=server)
    return {"ok": True, "marked": count}


@app.route("/api/notifications/clear", methods=["POST"])
def api_notifications_clear():
    guard = _api_auth_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or request.form.to_dict()
    server = data.get("server") or None
    kind = data.get("kind") or None
    direction = data.get("direction") or None
    count = notification_store.clear(server=server, kind=kind,
                                     direction=direction)
    return {"ok": True, "cleared": count}


@app.route("/api/chat", methods=["POST"])
def api_chat():
    guard = _api_auth_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or request.form.to_dict()
    sn = (data.get("shortname") or "").strip()
    msg = (data.get("message") or "").strip()
    if not sn:
        return {"ok": False, "error": "Server short name is required"}, 400
    if not msg:
        return {"ok": False, "error": "Message is required"}, 400
    out = bridge.send_chat(sn, msg)
    return {"ok": True, "output": out}


@app.route("/api/command", methods=["POST"])
def api_command():
    guard = _api_auth_guard()
    if guard:
        return guard
    data = request.get_json(silent=True) or request.form.to_dict()
    sn = data.get("shortname", "server")
    cmd = data.get("command", "")
    result = _run_admin_command(sn, cmd, data.get("replace_index"),
                                data.get("userid"))
    if result.get("needs_selection"):
        return result
    return {"ok": True, "output": result.get("output", [])}


@app.route("/api/events")
def api_events():
    guard = _auth_guard()
    if guard:
        return guard
    bridge.start()
    sub = bridge.events.subscribe()

    def gen():
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    ev = sub.get(timeout=30)
                except Exception:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            bridge.events.unsubscribe(sub)

    return Response(gen(), mimetype="text/event-stream")


def _apply_session_secret():
    data = config_store.load()
    secret = data.get("webcom", {}).get("session_secret")
    if secret:
        app.secret_key = secret


def main():
    _apply_session_secret()
    if config_store.is_configured():
        bridge.start()
    port = config_store.DEFAULT_PORT
    bind = config_store.DEFAULT_BIND
    app.run(host=bind, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
