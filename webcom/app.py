"""WebCom Flask application.

Routes:
  /setup            First-run wizard (web admin + TT servers + notifications).
  /login /logout    argon2 web dashboard auth.
  /                 Dashboard (live event stream via SSE).
  /servers          Manage multiple TT hosts (add/edit/remove).
  /notifications    Toggle ntfy/prowl/mgnotify/pushover/system per server.
  /pmsg             TTCom-PM compose/read (invisible to desktop clients).
  /admin            Kick / ckick / kb / ban list+add+delete / broadcast / etc.
  /api/command      POST a TTCom command; returns captured output.
  /api/events       SSE stream of live TTCom events.

Security: every route except /setup and /login requires the argon2 session.
WebCom binds to 0.0.0.0:2032 by default; override via docker-compose ports.
"""
from __future__ import annotations

import json
import time

from flask import (
    Flask, Blueprint, request, redirect, url_for, render_template_string,
    Response, session,
)

from . import config_store, auth
from .tt_bridge import bridge

app = Flask(__name__)
app.secret_key = "webcom-insecure-dev"  # replaced at runtime by session_secret
app.register_blueprint(auth.auth_bp)

INDEX_HTML = None  # loaded lazily to avoid import cycle


def _auth_guard():
    if not auth.is_authenticated():
        return redirect(url_for("auth.login"))
    return None


@app.route("/")
def index():
    # Fresh install (no web admin configured yet) -> straight to the setup
    # wizard, never to a login page with no user. This is the "get started" page.
    if not config_store.is_configured():
        return redirect(url_for("setup"))
    guard = _auth_guard()
    if guard:
        return guard
    from .pages import dashboard_html
    return render_template_string(dashboard_html())


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if config_store.is_configured():
        # Already set up; require login to re-enter.
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        # Step 1: web admin
        user = request.form.get("web_user", "admin").strip()
        pw = request.form.get("web_pass", "")
        if not user:
            return "Username required", 400
        if not pw:
            return "Password required", 400
        config_store.setup_web_admin(user, pw)
        # Step 2: TT servers (repeatable; at least one expected)
        try:
            servers = json.loads(request.form.get("servers_json", "[]"))
        except json.JSONDecodeError:
            return "Invalid servers JSON", 400
        if not isinstance(servers, list) or not servers:
            return "At least one server required", 400
        for s in servers:
            if not isinstance(s, dict):
                continue
            # Validate required fields
            if not s.get("shortname") or not s.get("host"):
                return "Server shortname and host required", 400
            try:
                s["tcpport"] = int(s.get("tcpport", 10333))
                s["udpport"] = int(s.get("udpport", 10333))
            except (ValueError, TypeError):
                return "Invalid port number", 400
            config_store.add_server(s)
        # Generate PowerCom's ttcom.conf from our store.
        config_store.generate_ttcom_conf()
        # Auto-connect after setup. If a server is unreachable, don't fail the
        # whole setup - surface it and let the dashboard retry.
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
    guard = _auth_guard()
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
        config_store.add_server(data)
        config_store.generate_ttcom_conf()
        return {"ok": True}
    if request.method == "DELETE":
        sn = (request.get_json(silent=True) or {}).get("shortname")
        if sn:
            config_store.delete_server(sn)
            config_store.generate_ttcom_conf()
        return {"ok": True}
    from .pages import servers_html
    return render_template_string(servers_html(config_store.list_servers()))


@app.route("/notifications", methods=["GET", "POST"])
def notifications():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        sn = data.get("shortname")
        s = config_store.get_server(sn)
        if s:
            for k in ("notifyloginout", "notifymessage", "systemnotify",
                      "ntfy", "prowl", "mgnotify", "pushover"):
                if k in data:
                    s[k] = data[k]
            config_store.add_server(s)
            config_store.generate_ttcom_conf()
        return {"ok": True}
    from .pages import notifications_html
    return render_template_string(notifications_html(config_store.list_servers()))


@app.route("/pmsg", methods=["GET", "POST"])
def pmsg():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        sn = data.get("shortname")
        target = data.get("target")
        text = data.get("text", "")
        # TTCom-PM: invisible to normal desktop clients (type 4, =sender= format).
        out = bridge.run_command(sn, f"pmsg {target} {text}")
        return {"ok": True, "output": out}
    from .pages import pmsg_html
    return render_template_string(pmsg_html(config_store.list_servers()))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    guard = _auth_guard()
    if guard:
        return guard
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        sn = data.get("shortname")
        cmd = data.get("command", "")
        out = bridge.run_command(sn, cmd)
        return {"ok": True, "output": out}
    from .pages import admin_html
    return render_template_string(admin_html(config_store.list_servers()))


@app.route("/logs")
def logs():
    guard = _auth_guard()
    if guard:
        return guard
    from .tt_bridge import bridge
    bridge.start()  # Ensure bridge is started and log capture active
    from .pages import logs_html
    return render_template_string(logs_html())


@app.route("/api/logs")
def api_logs():
    guard = _auth_guard()
    if guard:
        return guard, 403
    from .tt_bridge import bridge
    bridge.start()  # Ensure bridge is started and log capture active
    logs = bridge.logs.get_recent(200)
    # Format for display
    formatted = []
    for entry in logs:
        import datetime
        ts = datetime.datetime.fromtimestamp(entry["timestamp"]).strftime("%H:%M:%S")
        formatted.append(f"{ts} [{entry['level']}] {entry['source']}: {entry['message']}")
    return {"logs": "\n".join(formatted) or "No logs captured yet"}


@app.route("/api/debug/bridge")
def api_debug_bridge():
    """Debug endpoint to check bridge status."""
    guard = _auth_guard()
    if guard:
        return guard, 403
    from .tt_bridge import bridge
    return {
        "ready": bridge._ready,
        "cmd_exists": bridge._cmd is not None,
        "servers_configured": len(bridge.logs.get_recent(0)) > 0,  # dummy check
        "log_count": len(bridge.logs.get_recent(1000)),
    }


@app.route("/api/command", methods=["POST"])
def api_command():
    guard = _auth_guard()
    if guard:
        return guard, 403
    data = request.get_json(silent=True) or {}
    sn = data.get("shortname", "server")
    cmd = data.get("command", "")
    out = bridge.run_command(sn, cmd)
    return {"output": out}


@app.route("/api/events")
def api_events():
    guard = _auth_guard()
    if guard:
        return guard, 403
    sub = bridge.events.subscribe()

    def gen():
        yield "retry: 5000\n\n"
        # Send any backlog? No - just stream live.
        while True:
            try:
                ev = sub.get(timeout=30)
            except Exception:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(ev)}\n\n"

    return Response(gen(), mimetype="text/event-stream")


def _apply_session_secret():
    data = config_store.load()
    secret = data.get("webcom", {}).get("session_secret")
    if secret:
        app.secret_key = secret


def main():
    _apply_session_secret()
    port = config_store.DEFAULT_PORT
    bind = config_store.DEFAULT_BIND
    # NOTE: do NOT build the TTCom bridge here. PowerCom's conf.py reads
    # ttcom.conf at import time, and on a fresh container /data is empty (no
    # servers yet). The bridge is built lazily on first use, and /setup
    # regenerates ttcom.conf (with real servers) before calling connect_all().
    app.run(host=bind, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
