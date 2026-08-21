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
                    pass

                class _Output:
                    pass

                class _FileStream:
                    def __init__(self, *a, **k):
                        pass

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
            # container. Inject a minimal fake `prism` module so the import
            # chain succeeds without building native speech backends.
            import types as _types
            if "prism" not in sys.modules:
                _prism = _types.ModuleType("prism")
                _prism.BackendId = _types.SimpleNamespace(AV_SPEECH="AV_SPEECH",
                                                          NVDA="NVDA", JAWS="JAWS")
                _prism.Context = object
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

            # Wrap output methods to publish to our event queue.
            bridge = self

            class _WebComTTComCmd(CmdClass):
                def msg(self, text):
                    bridge.events.publish({"type": "output", "text": str(text)})

                def outputFromEvent(self, text):
                    bridge.events.publish({"type": "event", "text": str(text)})

                def speak(self, message, *a, **k):
                    # Headless: don't actually TTS; publish for the UI.
                    bridge.events.publish({"type": "speak", "text": str(message)})

            instance = _WebComTTComCmd(noAutoLogins=False)
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
            # Switch active server first, then run the command.
            self._cmd.onecmd(f"switch {shortname}")
            self._cmd.onecmd(command)
        except Exception as e:
            out.append(f"[error] {e}")
        # Drain whatever the command published (best-effort, short window).
        import time
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                ev = sub.get_nowait()
                if ev.get("type") in ("output", "event", "speak"):
                    out.append(ev.get("text", ""))
            except queue.Empty:
                if not self._cmd:
                    break
                # small yield
                time.sleep(0.05)
        return out

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
        servers = config_store.list_servers()
        log.info("connect_all: found %d servers", len(servers))
        self.logs.add("INFO", f"connect_all: found {len(servers)} servers", "webcom")
        if not servers:
            self.logs.add("WARNING", "connect_all: no servers configured", "webcom")
            return
        for s in servers:
            sn = s.get("shortname", "server")
            channel = s.get("channel")
            log.info("connect_all: processing server %s (channel=%s)", sn, channel)
            self.logs.add("INFO", f"connect_all: processing server {sn} (channel={channel})", "webcom")
            try:
                self._cmd.onecmd(f"switch {sn}")
                # Check current state
                cur_server = getattr(self._cmd, "curServer", None)
                st = getattr(cur_server, "state", "") if cur_server else ""
                log.info("connect_all: server %s current state=%s", sn, st)
                self.logs.add("INFO", f"connect_all: server {sn} current state={st}", "webcom")
                
                if st != "loggedIn":
                    self.events.publish({"type": "system", "text": f"Connecting to {sn}..."})
                    self._cmd.onecmd("connect")
                    # login() returns but actual login is async - wait for loggedIn state
                    self._cmd.onecmd("login")
                    # Wait for login to complete (state -> loggedIn)
                    deadline = time.time() + 15.0
                    last_state = ""
                    while time.time() < deadline:
                        cur_server = getattr(self._cmd, "curServer", None)
                        st = getattr(cur_server, "state", "") if cur_server else ""
                        if st != last_state:
                            log.info("connect_all: server %s state changed: %s -> %s", sn, last_state, st)
                            self.logs.add("INFO", f"connect_all: server {sn} state changed: {last_state} -> {st}", "webcom")
                            last_state = st
                        if st == "loggedIn":
                            break
                        if st == "loginError":
                            break
                        time.sleep(0.5)
                    cur_server = getattr(self._cmd, "curServer", None)
                    st = getattr(cur_server, "state", "") if cur_server else ""
                    log.info("connect_all: server %s state after login wait=%s", sn, st)
                    self.logs.add("INFO", f"connect_all: server {sn} state after login wait={st}", "webcom")
                    # Debug: dump server info
                    if cur_server:
                        try:
                            log.info("connect_all: server %s info: %s", sn, dict(cur_server.info))
                        except Exception:
                            pass
                    if st != "loggedIn":
                        self.events.publish({"type": "system", "text": f"Login to {sn} failed, state={st}"})
                        continue
                    self.events.publish({"type": "system", "text": f"Logged in to {sn}"})
                else:
                    self.events.publish({"type": "system", "text": f"Already logged in to {sn}"})
                
                if channel:
                    self._cmd.onecmd(f"join {channel}")
                    self.events.publish({"type": "system", "text": f"Joined {channel} on {sn}"})
            except Exception as e:
                import traceback
                log.exception("connect_all: failed for %s", sn)
                self.logs.add("ERROR", f"connect_all: failed for {sn}: {e}\n{traceback.format_exc()}", "webcom")
                self.events.publish({"type": "system", "text": f"Failed {sn}: {e}\n{traceback.format_exc()}"})


# Singleton bridge used by the web app.
bridge = TTComBridge()
