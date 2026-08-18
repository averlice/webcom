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


class TTComBridge:
    def __init__(self) -> None:
        self._cmd = None
        self._thread = None
        self._lock = threading.Lock()
        self.events = EventQueue()
        self._ready = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._ready:
                return
            self._cmd = self._build_cmd()
            self._ready = True

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
        """Connect + login to every configured server (autoLogin)."""
        if not self._ready:
            self.start()
        servers = []
        from . import config_store
        servers = config_store.list_servers()
        for s in servers:
            sn = s.get("shortname", "server")
            try:
                self._cmd.onecmd(f"switch {sn}")
                self._cmd.onecmd("connect")
                self._cmd.onecmd("login")
                self.events.publish({"type": "system", "text": f"Connecting to {sn}..."})
            except Exception as e:
                self.events.publish({"type": "system", "text": f"Failed {sn}: {e}"})


# Singleton bridge used by the web app.
bridge = TTComBridge()
