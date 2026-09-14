"""TTCom bridge: drives PowerCom's TTComCmd engine headlessly and exposes
its events + commands to the WebCom web layer via a queue (for SSE).

Key facts learned from reading the fork:
- TTComCmd is a `cmd.Cmd` REPL. We can instantiate it and call onecmd("...").
- conf.py imports at load and requires running from the PowerCom dir with
  ttcom.conf present. So we chdir to the app dir and generate ttcom.conf first.
- Output goes through self.msg(...) and outputFromEvent(...). We override those
  to push into an event queue for the browser.
- Multi-server: TTComCmd uses "switch <shortname>" to change the active server.
"""
from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable

from . import config_store
from . import notification_store

# The PowerCom app directory (where ttcom.conf + TTComCmd live).
_APP_DIR_ENV = os.environ.get("WEBCOM_APP_DIR", "")
if _APP_DIR_ENV:
    APP_DIR = Path(_APP_DIR_ENV)
else:
    APP_DIR = Path(__file__).resolve().parent.parent
# Normalize to a native OS path (Windows chdir rejects /c/wc form).
APP_DIR = Path(os.path.abspath(str(APP_DIR)))


class EventQueue:
    """Thread-safe pub/sub for SSE. One consumer per connection; events fanned out."""

    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except Exception:
                pass


class LogBuffer:
    """Captures log events for the web dashboard."""
    
    def __init__(self, max_size: int = 1000):
        self._logs: list[dict] = []
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def add(self, level: str, message: str, source: str = "webcom") -> None:
        import time
        entry = {
            "timestamp": time.time(),
            "level": level,
            "message": message,
            "source": source
        }
        with self._lock:
            self._logs.append(entry)
            if len(self._logs) > self._max_size:
                self._logs.pop(0)
    
    def get_recent(self, count: int = 100) -> list[dict]:
        with self._lock:
            return self._logs[-count:]
    
    def clear(self) -> None:
        with self._lock:
            self._logs.clear()


class TTComBridge:
    def __init__(self) -> None:
        self._cmd = None
        self._thread = None
        self._lock = threading.Lock()
        # TTComCmd has one mutable active-server pointer, so commands and a
        # config reload must never run concurrently.
        self._command_lock = threading.RLock()
        self.events = EventQueue()
        self.logs = LogBuffer()
        self._ready = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._ready:
                return
            self._cmd = self._build_cmd()
            self._ready = True
            # Set up log capture for web dashboard
            self._setup_log_capture()
            # Log startup message to verify capture works
            import logging
            logging.getLogger("webcom").info("WebCom bridge started, log capture active")
            # Auto-connect to servers in background after startup
            self._start_auto_connect()
            return

    def _setup_log_capture(self) -> None:
        """Attach a logging handler to capture logs for the web dashboard."""
        import logging
        
        class BridgeLogHandler(logging.Handler):
            def __init__(self, log_buffer):
                super().__init__()
                self.log_buffer = log_buffer
            
            def emit(self, record):
                try:
                    msg = self.format(record)
                    self.log_buffer.add(record.levelname, msg, record.name)
                except Exception:
                    pass
        
        handler = BridgeLogHandler(self.logs)
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        
        # Attach to webcom logger and root logger
        logging.getLogger("webcom").addHandler(handler)
        logging.getLogger("webcom").setLevel(logging.DEBUG)
        # Also capture root logger events
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

    def _start_auto_connect(self) -> None:
        """Start background thread to connect to servers and join channels."""
        import threading
        th = threading.Thread(target=self._auto_connect_task, daemon=True)
        th.start()

    def _auto_connect_task(self) -> None:
        """Background task: wait for PowerCom auto-login, then join channels."""
        import time
        import logging
        log = logging.getLogger("webcom")
        # Give PowerCom time to auto-login (it happens during readServers in __init__)
        time.sleep(2.0)
        log.info("Auto-connect task starting")
        self.logs.add("INFO", "Auto-connect task starting", "webcom")
        try:
            self.connect_all()
            log.info("Auto-connect task completed")
            self.logs.add("INFO", "Auto-connect task completed", "webcom")
        except Exception as e:
            import traceback
            log.exception("Auto-connect task failed")
            self.logs.add("ERROR", f"Auto-connect task failed: {e}\n{traceback.format_exc()}", "webcom")

    def _build_cmd(self):
        """Import TTComCmd from the PowerCom dir and wrap its output hooks.

        We use a normal `import` (after chdir + sys.path insert) rather than
        importlib.spec_from_file_location, because PowerCom's conf.py resolves
        itself via __file__ at import time and breaks under a spec load.
        """
        cwd = os.getcwd()
        os.chdir(str(APP_DIR))
        import sys
        if str(APP_DIR) not in sys.path:
            sys.path.insert(0, str(APP_DIR))
        try:
            # WebCom is headless: it does NOT do local audio. PowerCom's
            # audio.manager / audio.sound import the Windows-only `sound_lib`
            # (Bass) at module load, which cannot install on Linux slim. Inject
            # a minimal fake `sound_lib` package (main, output, stream submodules)
            # so the import chain succeeds. WebCom never actually plays audio.
            import types as _types
            if "sound_lib" not in sys.modules:
                _sound_lib = _types.ModuleType("sound_lib")
                _sl_main = _types.ModuleType("sound_lib.main")
                _sl_output = _types.ModuleType("sound_lib.output")
                _sl_stream = _types.ModuleType("sound_lib.stream")

                class _BassError(Exception):
                    code = 0

                class _Output:
                    def __init__(self, *a, **k):
                        self.volume = 100
                    def play(self, *a, **k): pass
                    def stop(self, *a, **k): pass

                class _FileStream:
                    def __init__(self, *a, **k):
                        self.frequency = 44100
                        self.volume = 1.0
                        self.is_playing = False
                        self.is_paused = False
                        self.is_stopped = True
                    def play(self, *a, **k): pass
                    def stop(self, *a, **k): pass
                    def pause(self, *a, **k): pass
                    def free(self, *a, **k): pass

                _sl_main.BassError = _BassError
                _sl_output.Output = _Output
                _sl_stream.FileStream = _FileStream
                _sound_lib.main = _sl_main
                _sound_lib.output = _sl_output
                _sound_lib.stream = _sl_stream
                sys.modules["sound_lib"] = _sound_lib
                sys.modules["sound_lib.main"] = _sl_main
                sys.modules["sound_lib.output"] = _sl_output
                sys.modules["sound_lib.stream"] = _sl_stream
            # WebCom is headless: it does NOT do local text-to-speech. It
            # publishes "speak" events to the browser instead. PowerCom's
            # speech.py imports the native `prism` CFFI binding (needs a
            # compiler + cffi at build time), which we don't want in the
            # container. Inject a fake `prism` module that forwards speech
            # events to the browser event stream.
            import types as _types
            if "prism" not in sys.modules:
                _prism = _types.ModuleType("prism")
                _prism.BackendId = _types.SimpleNamespace(AV_SPEECH="AV_SPEECH",
                                                          NVDA="NVDA", JAWS="JAWS")
                class _MockOutput:
                    class features:
                        supports_speak = True
                        supports_braille = True
                        supports_output = True
                        supports_stop = True
                        supports_refresh_voices = False
                        supports_count_voices = False
                    def speak(self, text, interrupt=True):
                        self.output(text, interrupt=interrupt)
                    def output(self, text, interrupt=True):
                        if text:
                            self_bridge = bridge
                            self_bridge.events.publish({"type": "speak", "text": str(text)})
                    def braille(self, text):
                        pass
                    def stop(self):
                        pass

                class _MockContext:
                    def create_best(self):
                        return _MockOutput()
                    def create_backend(self, *a, **k):
                        return _MockOutput()

                _prism.Context = _MockContext
                sys.modules["prism"] = _prism
            # PowerCom's mplib/conf.py resolves "itself" via sys.argv[0] at
            # import time. With `python -m` or `-c`, argv[0] isn't a usable
            # path and it raises "Run with full path; unable to find myself".
            # Point argv[0] at the real PowerCom entrypoint (absolute) so the
            # bootstrap resolves correctly.
            sys.argv[0] = str(APP_DIR / "powercom.py")
            # PowerCom's conf.py reads ttcom.conf from CWD at import time. The
            # authoritative copy lives in the data volume; copy it into APP_DIR
            # (gitignored) so the import succeeds. This keeps secrets in the
            # volume while satisfying PowerCom's load-time requirement.
            data_conf = config_store.TTCOM_CONF_PATH
            if not data_conf.is_file():
                # Fresh container: no servers configured yet. Generate a
                # defaults-only ttcom.conf so PowerCom's import-time conf read
                # succeeds; the wizard will regenerate it with real servers.
                config_store.generate_ttcom_conf()
            if data_conf.is_file():
                import shutil
                shutil.copyfile(str(data_conf), str(APP_DIR / "ttcom.conf"))
            import TTComCmd
            CmdClass = TTComCmd.TTComCmd
            # PowerCom's powercom_app.main() sets these on the conf singleton
            # before creating TTComCmd. ttapi.py reads conf.version at server
            # construction, so we set them here (mirrors powercom_app.main).
            import conf
            conf.conf.name = "WebCom"
            conf.conf.version = "2519"

            # Capture real server notifications: every event that PowerCom
            # processes (logins, logouts, PMs, channel/broadcast msgs, kicks,
            # status changes, joins/leaves, file events) is persisted to SQLite
            # and mirrored to the browser as a typed "notification" event so
            # the Notifications feed + PM inbox can show history and live up-
            # dates. We hook the event handler constructor because it central-
            # izes the server/event/runCommand triple in one place.
            import powercom_core.features as pcom_features

            # Event classification helpers. These turn a raw PowerCom event
            # into a stable storage kind + human label. TeamTalk user IDs are
            # ephemeral (they change every login), so labels are captured here
            # at event time and the userid is only kept for reference.
            def _notif_userid(event):
                parms = event.parms
                for key in ("userid", "srcuserid", "destuserid", "kickerid"):
                    if key in parms:
                        uid = str(parms[key])
                        if uid != "0":
                            return uid
                return None

            def _notif_kind(event):
                ev = getattr(event, "event", "") or ""
                if ev == "messagedeliver":
                    mtype = str(event.parms.type).strip() if "type" in event.parms else ""
                    return {"1": "pm", "2": "channel", "3": "broadcast", "4": "custom"}.get(mtype, "custom")
                return {
                    "loggedin": "login",
                    "loggedout": "logout",
                    "kicked": "kick",
                    "updateuser": "status",
                    "adduser": "joined",
                    "removeuser": "left",
                    "addfile": "file",
                    "removefile": "file",
                    "fileaccepted": "file",
                    "filecompleted": "file",
                    "serverupdate": "system",
                }.get(ev)

            def _notif_peer(server, event):
                uid = _notif_userid(event)
                if not uid:
                    return ""
                info = pcom_features.getUserInfo(server, uid)
                nickname = (info.get("nickname") or "").strip()
                username = (info.get("userName") or "").strip()
                if nickname and username:
                    return f"{nickname} ({username})"
                return nickname or username or f"user {uid}"

            def _notif_extra(event):
                extra = {}
                for key in ("userid", "srcuserid", "destuserid", "kickerid",
                            "chanid", "type", "msgtype"):
                    if key in event.parms:
                        extra[key] = str(event.parms[key])
                return extra

            _orig_event_init = pcom_features.PowerComEventHandler.__init__

            def _feature_event_init(self, server, event, runCommand):
                _orig_event_init(self, server, event, runCommand)
                # The original returns early (no prittyEvent) for command-caused,
                # self-caused, and not-logged-in events; we skip those too.
                text = getattr(self, "prittyEvent", None)
                if not text:
                    return
                kind = _notif_kind(event)
                if kind is None:
                    return
                peer = _notif_peer(server, event)
                row = notification_store.insert(
                    server=getattr(server, "shortname", ""),
                    kind=kind,
                    text=str(text),
                    direction="in",
                    peer=peer,
                    extra=_notif_extra(event),
                )
                bridge.events.publish({
                    "type": "notification",
                    "id": row["id"] if row else None,
                    "kind": kind,
                    "server": getattr(server, "shortname", ""),
                    "direction": "in",
                    "peer": peer,
                    "text": str(text),
                })

            pcom_features.PowerComEventHandler.__init__ = _feature_event_init

            # Wrap output methods to publish to our event queue.
            bridge = self

            class _WebComTTComCmd(CmdClass):
                def msg(self, *args, **kwargs):
                    text = " ".join(str(a) for a in args if a is not None)
                    if not text:
                        return
                    ev_type = "event" if kwargs.get("fromEvent") else "output"
                    bridge.events.publish({"type": ev_type, "text": text})

                def msgFromEvent(self, *args):
                    text = " ".join(str(a) for a in args if a is not None)
                    if text:
                        bridge.events.publish({"type": "event", "text": text})

                def outputFromEvent(self, *args, **kwargs):
                    text = " ".join(str(a) for a in args if a is not None)
                    if text:
                        bridge.events.publish({"type": "event", "text": text})

                def speak(self, message, *a, **k):
                    # Headless: publish for the UI.
                    if message:
                        bridge.events.publish({"type": "speak", "text": str(message)})

            # WebCom owns the connection lifecycle below. Letting TTComCmd
            # auto-login during construction races the bridge's reconnect and
            # means newly saved servers are not reliably picked up.
            instance = _WebComTTComCmd(noAutoLogins=True)
            instance.allowPython()
            return instance
        finally:
            os.chdir(cwd)

    # -- commands -----------------------------------------------------------
    def run_command(self, shortname: str, command: str) -> list[str]:
        """Run a TTCom command on a server. Returns captured output lines."""
        if not self._ready or self._cmd is None:
            self.start()
        out: list[str] = []
        # Capture via a temporary subscription.
        sub = self.events.subscribe()
        try:
            with self._command_lock:
                try:
                    # Switch active server first, then run the command.
                    if shortname:
                        self._cmd.onecmd(f"switch {shortname}")
                    self._cmd.onecmd(command)
                except Exception as e:
                    out.append(f"[error] {e}")
            # Drain output captured during execution
            import time
            deadline = time.time() + 0.35
            while time.time() < deadline:
                try:
                    ev = sub.get(timeout=0.05)
                    if ev.get("type") in ("output", "event", "speak"):
                        out.append(ev.get("text", ""))
                except queue.Empty:
                    if out:
                        # Output received and queue drained
                        break
        finally:
            self.events.unsubscribe(sub)
        return out

    def refresh_and_connect(self) -> None:
        """Reload saved servers and connect in the background.

        The dashboard can add or edit a server after TTComCmd was built. Its
        in-memory server list otherwise remains stale until the container is
        restarted, which is why saved servers appeared not to connect.
        """
        if not self._ready:
            self.start()
        threading.Thread(target=self._refresh_and_connect_task,
                         name="webcom-server-refresh", daemon=True).start()

    def _refresh_and_connect_task(self) -> None:
        try:
            with self._command_lock:
                self._cmd.onecmd("refresh")
                self.connect_all()
        except Exception as exc:
            self.logs.add("ERROR", f"Server refresh failed: {exc}", "webcom")
            self.events.publish({"type": "system", "text": f"Server refresh failed: {exc}"})

    def connect_all(self) -> None:
        """Ensure all configured servers are logged in and joined to their channels.
        If PowerCom's auto-login already connected, just join the channel.
        """
        import time
        import logging
        log = logging.getLogger("webcom")
        # Also log directly to buffer to ensure capture
        self.logs.add("INFO", "connect_all: starting", "webcom")
        if not self._ready:
            self.start()
        from . import config_store
        # Every saved server participates by default. A user can opt a server
        # out of startup connection with connectOnStart=false.
        servers = [server for server in config_store.list_servers()
                   if server.get("connectOnStart", True)]
        log.info("connect_all: found %d servers", len(servers))
        self.logs.add("INFO", f"connect_all: found {len(servers)} servers", "webcom")
        if not servers:
            self.logs.add("WARNING", "connect_all: no servers configured", "webcom")
            return
        with self._command_lock:
          for s in servers:
            sn = s.get("shortname", "server")
            channel = s.get("channel")
            log.info("connect_all: processing server %s (channel=%s)", sn, channel)
            self.logs.add("INFO", f"connect_all: processing server {sn} (channel={channel})", "webcom")
            try:
                self._cmd.onecmd(f"switch {sn}")
                # Check current state safely
                cur_server = self.get_server_obj(sn)
                st = getattr(cur_server, "state", "") if cur_server else ""
                log.info("connect_all: server %s current state=%s", sn, st)
                self.logs.add("INFO", f"connect_all: server {sn} current state={st}", "webcom")
                
                if st != "loggedIn":
                    self.events.publish({"type": "system", "text": f"Connecting to {sn}..."})
                    self._cmd.onecmd("login")
                    cur_server = self.get_server_obj(sn)
                    st = getattr(cur_server, "state", "") if cur_server else ""
                    log.info("connect_all: server %s state after login wait=%s", sn, st)
                    self.logs.add("INFO", f"connect_all: server {sn} state after login wait={st}", "webcom")
                    if st != "loggedIn":
                        error = getattr(cur_server, "lastError", None) or "No login response"
                        self.logs.add("WARNING", f"Login to {sn} failed: {error}", "webcom")
                        self.events.publish({"type": "system", "text": f"Login to {sn} failed: {error}"})
                        continue
                    self.events.publish({"type": "system", "text": f"Logged in to {sn}"})
                else:
                    self.events.publish({"type": "system", "text": f"Already logged in to {sn}"})
                
                if channel:
                    self.events.publish({"type": "system", "text": f"Joining {channel} on {sn}"})
            except Exception as e:
                import traceback
                log.exception("connect_all: failed for %s", sn)
                self.logs.add("ERROR", f"connect_all: failed for {sn}: {e}\n{traceback.format_exc()}", "webcom")
                self.events.publish({"type": "system", "text": f"Failed {sn}: {e}"})

    def get_server_obj(self, shortname: str):
        if not self._cmd or not hasattr(self._cmd, "servers"):
            return None
        return self._cmd.servers.get(shortname)

    def get_servers_status(self) -> list[dict]:
        """Returns connection and channel status for all configured servers."""
        from . import config_store
        result = []
        cfg_servers = config_store.list_servers()
        for s in cfg_servers:
            sn = s.get("shortname", "")
            server_obj = self.get_server_obj(sn)
            state = getattr(server_obj, "state", "disconnected") if server_obj else "offline"
            chan_name = ""
            if server_obj and getattr(server_obj, "me", None):
                cid = getattr(server_obj.me, "chanid", None)
                if cid is not None and hasattr(server_obj, "channelname"):
                    try:
                        chan_name = server_obj.channelname(cid)
                    except Exception:
                        pass
            users_count = len(getattr(server_obj, "users", {})) if server_obj else 0
            result.append({
                "shortname": sn,
                "host": s.get("host", ""),
                "port": s.get("tcpport", 10333),
                "nickname": s.get("nickname", "WebCom"),
                "state": state,
                "channel": chan_name or s.get("channel", "/"),
                "users_count": users_count,
                "connectOnStart": s.get("connectOnStart", True),
            })
        return result

    def connect_server(self, shortname: str) -> None:
        """Connect and log in to a specific server in background."""
        if not self._ready:
            self.start()
        def _task():
            with self._command_lock:
                try:
                    self.events.publish({"type": "system", "text": f"Connecting to {shortname}..."})
                    self._cmd.onecmd(f"switch {shortname}")
                    self._cmd.onecmd("login")
                    server_obj = self.get_server_obj(shortname)
                    st = getattr(server_obj, "state", "") if server_obj else ""
                    if st == "loggedIn":
                        self.events.publish({"type": "system", "text": f"Connected to {shortname}"})
                    else:
                        err = getattr(server_obj, "lastError", None) or "Login failed"
                        self.events.publish({"type": "system", "text": f"Failed {shortname}: {err}"})
                except Exception as exc:
                    self.events.publish({"type": "system", "text": f"Connection error {shortname}: {exc}"})
        threading.Thread(target=_task, name=f"webcom-connect-{shortname}", daemon=True).start()

    def disconnect_server(self, shortname: str) -> None:
        """Disconnect from a specific server."""
        if not self._ready:
            self.start()
        def _task():
            with self._command_lock:
                try:
                    self._cmd.onecmd(f"switch {shortname}")
                    self._cmd.onecmd("disconnect")
                    self.events.publish({"type": "system", "text": f"Disconnected from {shortname}"})
                except Exception as exc:
                    self.events.publish({"type": "system", "text": f"Disconnect error {shortname}: {exc}"})
        threading.Thread(target=_task, name=f"webcom-disconnect-{shortname}", daemon=True).start()

    def send_chat(self, shortname: str, message: str) -> list[str]:
        """Send a channel message on the specified server."""
        return self.run_command(shortname, f"cmsg {message}")

    def send_pm(self, shortname: str, target: str, message: str, is_ttcom: bool = False) -> list[str]:
        """Send a private message (umsg for standard TT, pmsg for TTCom invisible PM).

        target may be a nickname/username fragment or an exact "#userid".
        Use an exact #userid (obtained from find_users) when the name is
        ambiguous, because PowerCom's interactive user picker cannot run
        headlessly. Successful sends are recorded as direction=out PMs in
        the notification store, labelled with the recipient's nickname+(user).
        """
        cmd = "pmsg" if is_ttcom else "umsg"
        out = self.run_command(shortname, f"{cmd} {target} {message}")
        # Record the send only if it did not error. run_command prepends an
        # [error] line when PowerCom raised.
        failed = any(ln.startswith("[error]") for ln in out)
        if not failed:
            peer = self._pm_peer_label(shortname, target)
            notification_store.insert(
                server=shortname,
                kind="pm",
                text=message or "",
                direction="out",
                peer=peer,
                extra={"is_ttcom": is_ttcom},
            )
        return out

    def _pm_peer_label(self, shortname: str, target: str) -> str:
        """Best-effort human label (nickname (username)) for a PM recipient."""
        matches = self.find_users(shortname, target)
        if not matches:
            return target or ""
        if target.startswith("#") and target[1:].isdigit():
            for m in matches:
                if m.get("userid") == target[1:]:
                    return self._label_from_match(m)
        if len(matches) == 1:
            return self._label_from_match(matches[0])
        return target or ""

    @staticmethod
    def _label_from_match(match: dict) -> str:
        nickname = (match.get("nickname") or "").strip().strip('"')
        username = (match.get("username") or "").strip()
        if nickname and username:
            return f"{nickname} ({username})"
        return nickname or username or (f"user {match.get('userid')}" if match.get("userid") else "")

    def find_users(self, shortname: str, target: str) -> list[dict]:
        """Return all users on a server whose nickname/username matches target.

        Mirrors PowerCom's userMatch containment rules but returns the full
        match list instead of prompting interactively, so the web UI can render
        ambiguous names as a dropdown. Each entry has userid, nickname and
        username so a PM can then be sent to an exact "#userid".
        """
        if not self._ready or self._cmd is None:
            self.start()
        target = (target or "").strip()
        if not target:
            return []
        with self._command_lock:
            try:
                if shortname:
                    self._cmd.onecmd(f"switch {shortname}")
                server = self._cmd.curServer
            except Exception as exc:
                self.logs.add("WARNING", f"find_users: cannot switch to {shortname}: {exc}", "webcom")
                return []
            users = list(server.users.values())
            if target.startswith("#") and target[1:].isdigit():
                matches = [u for u in users if str(u.userid) == target[1:]]
            else:
                needle = target.lower()
                matches = [u for u in users
                           if needle in server.nonEmptyNickname(u, "dnc").lower()]
            results = []
            for u in matches:
                nickname = server.nonEmptyNickname(u, "dnc")
                username = u.get("username") or ""
                results.append({
                    "userid": str(u.userid),
                    "nickname": nickname,
                    "username": username,
                    "label": self._label_from_match({"nickname": nickname, "username": username, "userid": str(u.userid)}),
                })
            return results


# Singleton bridge used by the web app.
bridge = TTComBridge()
