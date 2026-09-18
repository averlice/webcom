"""WebCom page templates (server-rendered, screen-reader friendly).

Accessibility and screen-reader design notes:
- Every interactive control has an explicit <label for="..."> linked to input id.
- The live event stream uses an ARIA live region (aria-live="polite", aria-relevant="additions")
  so screen readers announce new TeamTalk events (joins, messages, kicks) as they arrive.
- Visual glyphs (like checkmarks) are avoided in favor of clear descriptive text ("Enabled", "Disabled").
- Headings are used strictly in hierarchical order without visual-only cues.
- Navigation uses semantic lists with aria-current="page" to clearly convey location.
- Live status messages are announced via ARIA live regions without interrupting user typing.
"""
from __future__ import annotations

import html
import json

BASE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - WebCom</title>
<style>
  :root {{
    --bg: #ffffff;
    --text: #1a1a1a;
    --text-muted: #555555;
    --focus: #005fcc;
    --border: #cccccc;
    --card-bg: #f8f9fa;
    --primary: #0b5ed7;
    --primary-hover: #0a58ca;
    --danger: #b02a37;
    --danger-bg: #f8d7da;
    --success-bg: #d1e7dd;
    --success-text: #0f5132;
    --info-bg: #cff4fc;
    --info-text: #055160;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #121212;
      --text: #e0e0e0;
      --text-muted: #aaaaaa;
      --focus: #4da3ff;
      --border: #444444;
      --card-bg: #1e1e1e;
      --primary: #2563eb;
      --primary-hover: #3b82f6;
      --danger: #dc3545;
      --danger-bg: #3f1a1d;
      --success-bg: #0f3d26;
      --success-text: #75b798;
      --info-bg: #052c38;
      --info-text: #6edff6;
    }}
  }}
  body {{
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    margin: 1rem auto;
    padding: 0 1rem;
    max-width: 76rem;
    background: var(--bg);
    color: var(--text);
  }}
  a, button, input, select, textarea {{ font: inherit; color: inherit; }}
  a {{ color: var(--primary); text-decoration: underline; }}
  a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {{
    outline: 3px solid var(--focus);
    outline-offset: 3px;
  }}
  .skip-link {{
    position: absolute;
    left: -9999px;
    top: 0;
    background: #ffffff;
    color: #000000;
    padding: .75rem 1rem;
    z-index: 100;
    font-weight: bold;
    border: 2px solid var(--focus);
  }}
  .skip-link:focus {{ left: 1rem; top: 1rem; }}
  nav ul {{
    list-style: none;
    padding: 0;
    margin: 0 0 1.5rem 0;
    display: flex;
    flex-wrap: wrap;
    gap: .5rem .75rem;
  }}
  nav li {{ margin: 0; }}
  nav a {{
    display: inline-block;
    padding: .4rem .75rem;
    border-radius: 4px;
    text-decoration: none;
    border: 1px solid var(--border);
  }}
  nav a[aria-current="page"] {{
    background: var(--primary);
    color: #ffffff;
    border-color: var(--primary);
    font-weight: bold;
  }}
  nav a:hover:not([aria-current="page"]) {{
    background: var(--card-bg);
    text-decoration: underline;
  }}
  fieldset {{
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem;
    margin: 1rem 0;
    background: var(--card-bg);
  }}
  legend {{
    font-weight: bold;
    padding: 0 .5rem;
  }}
  .form-group {{ margin-bottom: 1rem; }}
  .form-group label {{
    display: block;
    font-weight: 500;
    margin-bottom: .25rem;
  }}
  .form-group .hint {{
    font-size: .875rem;
    color: var(--text-muted);
    margin-top: .25rem;
  }}
  input[type="text"], input[type="password"], input[type="number"], select, textarea {{
    width: 100%;
    max-width: 36rem;
    box-sizing: border-box;
    padding: .5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
  }}
  button, input[type="submit"] {{
    cursor: pointer;
    padding: .5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--card-bg);
    font-weight: 500;
  }}
  button.primary, input[type="submit"].primary {{
    background: var(--primary);
    color: #ffffff;
    border-color: var(--primary);
  }}
  button.danger {{
    background: var(--danger);
    color: #ffffff;
    border-color: var(--danger);
  }}
  .table-wrap {{ overflow-x: auto; margin: 1rem 0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: .5rem .75rem; border: 1px solid var(--border); text-align: left; }}
  th {{ background: var(--card-bg); }}
  .status-badge {{
    display: inline-block;
    padding: .2rem .5rem;
    border-radius: 4px;
    font-size: .875rem;
    font-weight: bold;
  }}
  .status-online {{ background: var(--success-bg); color: var(--success-text); }}
  .status-offline {{ background: var(--danger-bg); color: var(--danger); }}
  .status-pending {{ background: var(--info-bg); color: var(--info-text); }}
  .actions-group {{ display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }}
  .status-message {{
    padding: .5rem .75rem;
    border-radius: 4px;
    margin: .5rem 0;
    border: 1px solid var(--border);
    background: var(--card-bg);
  }}
  .nav-badge {{
    display: inline-block;
    margin-left: .35rem;
    padding: 0 .45rem;
    border-radius: 999px;
    background: var(--danger);
    color: #ffffff;
    font-size: .75rem;
    font-weight: bold;
  }}
  .notif-item {{
    padding: .4rem .6rem;
    border-bottom: 1px solid var(--border);
    word-break: break-word;
  }}
  .notif-item.unread {{ font-weight: bold; }}
  .notif-kind {{ color: var(--text-muted); }}
</style>
</head>
<body>
<a class="skip-link" href="#main">Skip to main content</a>
<header>
  <nav aria-label="Main Navigation">
    <ul>
      <li><a href="/" {nav_dashboard}>Dashboard</a></li>
      <li><a href="/servers" {nav_servers}>Servers</a></li>
      <li><a href="/users" {nav_users}>Users</a></li>
      <li><a href="/notifications" {nav_notifications}>Notifications <span id="notif_badge" class="nav-badge" style="display:none;"></span></a></li>
      <li><a href="/settings" {nav_settings}>Settings</a></li>
      <li><a href="/pmsg" {nav_pmsg}>Private Messages</a></li>
      <li><a href="/admin" {nav_admin}>Admin</a></li>
      <li><a href="/logs" {nav_logs}>Logs</a></li>
      <li><a href="/logout">Logout</a></li>
    </ul>
  </nav>
</header>
<main id="main" tabindex="-1">
<h1>{title}</h1>
{content}
</main>
<script>
(function() {{
  function refreshBadge() {{
    fetch('/api/notifications/unread').then(function(r) {{ return r.json(); }}).then(function(d) {{
      var b = document.getElementById('notif_badge');
      if (b && d.count > 0) {{ b.textContent = d.count; b.style.display = 'inline'; }}
      else if (b) {{ b.style.display = 'none'; }}
    }}).catch(function() {{}});
  }}
  refreshBadge();
  setInterval(refreshBadge, 15000);
}})();
</script>
</body>
</html>
"""


def _wrap(title: str, content: str, active: str = "dashboard") -> str:
    nav_attrs = {
        "nav_dashboard": 'aria-current="page"' if active == "dashboard" else "",
        "nav_servers": 'aria-current="page"' if active == "servers" else "",
        "nav_users": 'aria-current="page"' if active == "users" else "",
        "nav_notifications": 'aria-current="page"' if active == "notifications" else "",
        "nav_settings": 'aria-current="page"' if active == "settings" else "",
        "nav_pmsg": 'aria-current="page"' if active == "pmsg" else "",
        "nav_admin": 'aria-current="page"' if active == "admin" else "",
        "nav_logs": 'aria-current="page"' if active == "logs" else "",
    }
    return BASE.format(title=title, content=content, **nav_attrs)


# ---------------------------------------------------------------------------
# Setup Wizard
# ---------------------------------------------------------------------------
def setup_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Setup Wizard - WebCom</title>
<style>
  body { font-family: system-ui, sans-serif; line-height: 1.6; margin: 1rem auto; padding: 0 1rem; max-width: 60rem; }
  a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid #005fcc; outline-offset: 3px; }
  fieldset { border: 1px solid #ccc; border-radius: 6px; padding: 1rem; margin: 1rem 0; background: #fdfdfd; }
  legend { font-weight: bold; padding: 0 .5rem; }
  .field { margin-bottom: 1rem; }
  label { display: block; font-weight: 500; margin-bottom: .25rem; }
  input[type="text"], input[type="password"], input[type="number"] { width: 100%; max-width: 28rem; padding: .5rem; box-sizing: border-box; }
  button { cursor: pointer; padding: .5rem 1rem; }
  button.primary { background: #0b5ed7; color: #fff; border: 1px solid #0b5ed7; border-radius: 4px; font-weight: bold; }
</style>
</head>
<body>
<main id="main">
<h1>WebCom First-Run Setup</h1>
<p>Welcome to WebCom. Configure your web dashboard admin user and initial TeamTalk server below.</p>
<form method="post" id="wizard" onsubmit="return collect(event)">
<fieldset>
  <legend>Step 1: Dashboard Login</legend>
  <div class="field">
    <label for="web_user">Dashboard Admin Username</label>
    <input id="web_user" name="web_user" value="admin" required autocomplete="username">
  </div>
  <div class="field">
    <label for="web_pass">Dashboard Admin Password</label>
    <input id="web_pass" name="web_pass" type="password" required autocomplete="new-password">
  </div>
</fieldset>

<fieldset>
  <legend>Step 2: TeamTalk Servers</legend>
  <p>Add at least one TeamTalk server. Passwords are saved in the local data volume only.</p>
  <div id="servers_container"></div>
  <button type="button" onclick="addServer()">Add another server</button>
</fieldset>

<p style="margin-top:1.5rem;">
  <button type="submit" class="primary">Save and Start WebCom</button>
</p>
</form>
</main>
<script>
var srvCount = 0;
function addServer() {
  srvCount++;
  var idx = srvCount;
  var d = document.createElement('fieldset');
  d.className = 'srv-entry';
  d.id = 'srv_' + idx;
  d.innerHTML = '<legend>Server ' + idx + '</legend>' +
    '<div class="field"><label for="sn_' + idx + '">Server Short Name (letters/numbers, no spaces)</label>' +
    '<input id="sn_' + idx + '" name="sn" required placeholder="e.g. main"></div>' +
    '<div class="field"><label for="host_' + idx + '">Server Host</label>' +
    '<input id="host_' + idx + '" name="host" required placeholder="e.g. tt.example.com"></div>' +
    '<div class="field"><label for="tcp_' + idx + '">TCP Port</label>' +
    '<input id="tcp_' + idx + '" name="tcpport" type="number" value="10333" required></div>' +
    '<div class="field"><label for="udp_' + idx + '">UDP Port</label>' +
    '<input id="udp_' + idx + '" name="udpport" type="number" value="10333" required></div>' +
    '<div class="field"><label for="user_' + idx + '">Username (optional)</label>' +
    '<input id="user_' + idx + '" name="username"></div>' +
    '<div class="field"><label for="pass_' + idx + '">Password (optional)</label>' +
    '<input id="pass_' + idx + '" name="password" type="password"></div>' +
    '<div class="field"><label for="nick_' + idx + '">Nickname</label>' +
    '<input id="nick_' + idx + '" name="nickname" value="WebCom" required></div>' +
    '<div class="field"><label for="chan_' + idx + '">Auto-join Channel Path</label>' +
    '<input id="chan_' + idx + '" name="channel" value="/text/"></div>' +
    '<div class="field"><label><input type="checkbox" name="connectOnStart" checked> Connect on startup</label></div>' +
    '<div class="field"><label><input type="checkbox" name="encrypted"> Encrypted connection (TLS)</label></div>';
  document.getElementById('servers_container').appendChild(d);
}
addServer();

function collect(e) {
  var entries = document.querySelectorAll('.srv-entry');
  var servers = [];
  for (var i = 0; i < entries.length; i++) {
    var s = entries[i];
    var sn = s.querySelector('[name=sn]').value.trim();
    var host = s.querySelector('[name=host]').value.trim();
    if (!sn || !host) {
      alert('Short name and host are required for each server.');
      if (e) e.preventDefault();
      return false;
    }
    servers.push({
      shortname: sn,
      host: host,
      tcpport: parseInt(s.querySelector('[name=tcpport]').value) || 10333,
      udpport: parseInt(s.querySelector('[name=udpport]').value) || 10333,
      username: s.querySelector('[name=username]').value.trim(),
      password: s.querySelector('[name=password]').value,
      nickname: s.querySelector('[name=nickname]').value.trim() || 'WebCom',
      channel: s.querySelector('[name=channel]').value.trim() || '/text/',
      connectOnStart: s.querySelector('[name=connectOnStart]').checked,
      encrypted: s.querySelector('[name=encrypted]').checked,
      autoLogin: 1
    });
  }
  var f = document.getElementById('wizard');
  var inp = document.getElementById('hidden_servers_json');
  if (!inp) {
    inp = document.createElement('input');
    inp.type = 'hidden';
    inp.name = 'servers_json';
    inp.id = 'hidden_servers_json';
    f.appendChild(inp);
  }
  inp.value = JSON.stringify(servers);
  return true;
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def _conn_action(sn: str, state: str) -> str:
    """Return the Connect/Disconnect control for a server based on its state.

    Shows Disconnect only when already connected, Connect only when not
    connected, and a pending label while a login is in progress.
    """
    if state == "loggedIn":
        return (f'<button type="button" onclick="disconnectServer(\'{sn}\')" '
                f'aria-label="Disconnect server {sn}">Disconnect</button>')
    if state == "loggingIn":
        return '<span class="status-badge status-pending">Connecting...</span>'
    return (f'<button type="button" onclick="connectServer(\'{sn}\')" '
            f'aria-label="Connect server {sn}">Connect</button>')


def dashboard_html(servers: list[dict] | None = None, servers_status: list[dict] | None = None) -> str:
    servers = servers or []
    servers_status = servers_status or []
    server_opts = "".join(f'<option value="{html.escape(s.get("shortname", ""))}">{html.escape(s.get("shortname", ""))}</option>' for s in servers)

    status_rows = []
    for s in servers_status:
        sn = html.escape(s.get("shortname", ""))
        st = html.escape(s.get("state", "offline"))
        badge_class = "status-online" if st == "loggedIn" else ("status-pending" if st == "loggingIn" else "status-offline")
        chan = html.escape(s.get("channel", "/"))
        ucnt = s.get("users_count", 0)
        status_rows.append(
            f'<tr>'
            f'<td><strong>{sn}</strong></td>'
            f'<td><span class="status-badge {badge_class}">{st}</span></td>'
            f'<td>{chan}</td>'
            f'<td>{ucnt}</td>'
            f'<td><div class="actions-group">'
            f'{_conn_action(sn, st)}'
            f'</div></td>'
            f'</tr>'
        )
    status_table = (
        '<div class="table-wrap"><table>'
        '<thead><tr><th scope="col">Server</th><th scope="col">Status</th><th scope="col">Channel</th><th scope="col">Users</th><th scope="col">Actions</th></tr></thead>'
        f'<tbody>{"".join(status_rows)}</tbody>'
        '</table></div>' if status_rows else '<p>No servers configured yet. <a href="/servers">Add a server</a>.</p>'
    )

    content = f"""
<h2>Server Status</h2>
{status_table}

<h2>Send Message to Channel</h2>
<form id="chatForm" onsubmit="sendChat(event)">
  <div class="form-group">
    <label for="chat_server">Target Server</label>
    <select id="chat_server" name="shortname">{server_opts}</select>
  </div>
  <div class="form-group">
    <label for="chat_message">Message to Channel</label>
    <input id="chat_message" name="message" required placeholder="Type a message to send to the current channel..." autocomplete="off">
  </div>
  <button type="submit" class="primary">Send Message</button>
  <div id="chat_status" role="status" aria-live="polite" class="status-message" style="display:none;"></div>
</form>

<h2>Live Events &amp; Messages</h2>
<p id="event-help">New messages, user joins, and events are announced automatically as they arrive.</p>
<div class="actions-group" style="margin-bottom:.5rem;">
  <fieldset style="display:inline-flex;gap:1rem;padding:.25rem .75rem;margin:0;align-items:center;">
    <legend>Filter Events</legend>
    <label><input type="radio" name="evt_filter" value="all" checked onchange="setFilter('all')"> All</label>
    <label><input type="radio" name="evt_filter" value="chat" onchange="setFilter('chat')"> Chat only</label>
    <label><input type="radio" name="evt_filter" value="speak" onchange="setFilter('speak')"> Speech only</label>
    <label><input type="radio" name="evt_filter" value="event" onchange="setFilter('event')"> Events only</label>
  </fieldset>
  <button type="button" onclick="clearEvents()">Clear event log</button>
  <label><input type="checkbox" id="pause_announcements" onchange="togglePause()"> Pause live announcements</label>
</div>

<ol aria-live="polite" aria-relevant="additions" aria-atomic="false" aria-describedby="event-help" id="events"
    style="font-family:monospace;max-height:55vh;overflow-y:auto;padding:.75rem 1rem;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;list-style-type:none;margin:0;">
</ol>

<script>
var currentFilter = 'all';
var isPaused = false;
var es = new EventSource('/api/events');

es.onmessage = function(e) {{
  try {{
    var d = JSON.parse(e.data);
    var evType = d.type || 'event';
    var text = d.text || '';
    if (!text) return;

    var now = new Date();
    var timeStr = now.toTimeString().split(' ')[0];
    var line = '[' + timeStr + '] [' + evType + '] ' + text;

    var box = document.getElementById('events');
    var item = document.createElement('li');
    item.textContent = line;
    item.setAttribute('data-type', evType);

    if (currentFilter !== 'all' && evType !== currentFilter) {{
      item.style.display = 'none';
    }}

    box.appendChild(item);
    box.scrollTop = box.scrollHeight;
  }} catch (err) {{
    console.error('Failed to parse event:', err);
  }}
}};

function setFilter(filter) {{
  currentFilter = filter;
  var items = document.querySelectorAll('#events li');
  items.forEach(function(item) {{
    var t = item.getAttribute('data-type');
    if (filter === 'all' || t === filter) {{
      item.style.display = '';
    }} else {{
      item.style.display = 'none';
    }}
  }});
}}

function clearEvents() {{
  document.getElementById('events').innerHTML = '';
}}

function togglePause() {{
  isPaused = document.getElementById('pause_announcements').checked;
  var box = document.getElementById('events');
  if (isPaused) {{
    box.setAttribute('aria-live', 'off');
  }} else {{
    box.setAttribute('aria-live', 'polite');
  }}
}}

async function sendChat(e) {{
  e.preventDefault();
  var sn = document.getElementById('chat_server').value;
  var msgInput = document.getElementById('chat_message');
  var msg = msgInput.value.trim();
  var statusDiv = document.getElementById('chat_status');
  if (!msg) return;

  statusDiv.style.display = 'block';
  statusDiv.textContent = 'Sending message to ' + sn + '...';

  try {{
    var resp = await fetch('/api/chat', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ shortname: sn, message: msg }})
    }});
    var res = await resp.json();
    if (res.ok) {{
      statusDiv.textContent = 'Message sent to ' + sn + '.';
      msgInput.value = '';
      msgInput.focus();
    }} else {{
      statusDiv.textContent = 'Error: ' + (res.error || 'Failed to send');
    }}
  }} catch (err) {{
    statusDiv.textContent = 'Network error: ' + err;
  }}
}}

async function connectServer(sn) {{
  try {{
    await fetch('/servers/connect/' + sn, {{ method: 'POST' }});
  }} catch (e) {{
    alert('Failed to connect: ' + e);
  }}
}}

async function disconnectServer(sn) {{
  try {{
    await fetch('/servers/disconnect/' + sn, {{ method: 'POST' }});
  }} catch (e) {{
    alert('Failed to disconnect: ' + e);
  }}
}}
</script>
"""
    return _wrap("Dashboard", content, active="dashboard")


# ---------------------------------------------------------------------------
# Servers Management
# ---------------------------------------------------------------------------
def servers_html(servers: list[dict], servers_status: list[dict] | None = None) -> str:
    status_map = {}
    if servers_status:
        for s in servers_status:
            status_map[s.get("shortname", "")] = s

    rows = []
    for s in servers:
        sn = html.escape(s.get("shortname", ""))
        host = html.escape(str(s.get("host", "")))
        tcp = s.get("tcpport", 10333)
        user = html.escape(str(s.get("username", ""))) or "(anonymous)"
        st_info = status_map.get(s.get("shortname", ""), {})
        state = html.escape(st_info.get("state", "offline"))
        badge_class = "status-online" if state == "loggedIn" else ("status-pending" if state == "loggingIn" else "status-offline")

        rows.append(
            f'<tr>'
            f'<td><strong>{sn}</strong></td>'
            f'<td><span class="status-badge {badge_class}">{state}</span></td>'
            f'<td>{host}:{tcp}</td>'
            f'<td>{user}</td>'
            f'<td><div class="actions-group">'
            f'<button type="button" onclick="editServer(\'{sn}\')" aria-label="Edit server {sn}">Edit</button>'
            f'{_conn_action(sn, state)}'
            f'<button type="button" class="danger" onclick="deleteServer(\'{sn}\')" aria-label="Delete server {sn}">Delete</button>'
            f'</div></td>'
            f'</tr>'
        )

    server_table = (
        '<div class="table-wrap"><table>'
        '<thead><tr><th scope="col">Short Name</th><th scope="col">Status</th><th scope="col">Host &amp; Port</th><th scope="col">User</th><th scope="col">Actions</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></div>' if rows else '<p>No servers configured yet.</p>'
    )

    content = f"""
<h2>Configured Servers</h2>
{server_table}

<div id="status_alert" role="status" aria-live="polite" class="status-message" style="display:none;"></div>

<h2 id="form_heading">Add a Server</h2>
<form id="serverForm" method="post" action="/servers" onsubmit="saveServer(event)">
  <div class="form-group">
    <label for="f_shortname">Server Short Name</label>
    <input id="f_shortname" name="shortname" required autocomplete="off">
    <div class="hint">A unique identifier with no spaces (e.g. main, ttcommunity).</div>
  </div>
  <div class="form-group">
    <label for="f_host">Host Address</label>
    <input id="f_host" name="host" required placeholder="e.g. tt.example.com">
  </div>
  <div class="form-group">
    <label for="f_tcpport">TCP Port</label>
    <input id="f_tcpport" name="tcpport" type="number" value="10333" required>
  </div>
  <div class="form-group">
    <label for="f_udpport">UDP Port</label>
    <input id="f_udpport" name="udpport" type="number" value="10333" required>
  </div>
  <div class="form-group">
    <label for="f_username">Username (leave blank if none)</label>
    <input id="f_username" name="username">
  </div>
  <div class="form-group">
    <label for="f_password">Password</label>
    <input id="f_password" name="password" type="password" autocomplete="new-password">
  </div>
  <div class="form-group">
    <label for="f_nickname">Display Nickname</label>
    <input id="f_nickname" name="nickname" value="WebCom" required>
  </div>
  <div class="form-group">
    <label for="f_status">Status Message</label>
    <input id="f_status" name="status">
  </div>
  <div class="form-group">
    <label for="f_channel">Channel Path to Join</label>
    <input id="f_channel" name="channel" value="/text/">
    <div class="hint">Canonical channel path format, e.g. /text/ or /</div>
  </div>
  <div class="form-group">
    <label><input id="f_connect_on_start" name="connectOnStart" type="checkbox" value="1" checked> Connect on startup</label>
  </div>
  <div class="form-group">
    <label><input id="f_auto_reconnect" name="autoReconnect" type="checkbox" value="1"> Auto-reconnect after a connection drop</label>
  </div>
  <div class="form-group">
    <label><input id="f_encrypted" name="encrypted" type="checkbox" value="1"> Encrypted connection (TLS)</label>
  </div>
  <input type="hidden" id="f_previous_shortname" name="previous_shortname">
  <div class="actions-group">
    <button type="submit" class="primary" id="save_btn">Save Server</button>
    <button type="button" id="cancel_edit_btn" onclick="resetForm()" style="display:none;">Cancel Edit</button>
  </div>
</form>

<script>
function showAlert(msg) {{
  var d = document.getElementById('status_alert');
  d.style.display = 'block';
  d.textContent = msg;
}}

async function editServer(sn) {{
  try {{
    const r = await fetch('/servers/edit/' + sn);
    const d = await r.json();
    if (!d.ok) return alert(d.error);
    const s = d.server;
    document.getElementById('form_heading').textContent = 'Edit Server: ' + s.shortname;
    document.getElementById('f_previous_shortname').value = s.shortname;
    document.getElementById('f_shortname').value = s.shortname;
    document.getElementById('f_host').value = s.host || '';
    document.getElementById('f_tcpport').value = s.tcpport || 10333;
    document.getElementById('f_udpport').value = s.udpport || 10333;
    document.getElementById('f_username').value = s.username || '';
    document.getElementById('f_password').value = s.password || '';
    document.getElementById('f_nickname').value = s.nickname || 'WebCom';
    document.getElementById('f_status').value = s.status || '';
    document.getElementById('f_channel').value = s.channel || '/text/';
    document.getElementById('f_connect_on_start').checked = s.connectOnStart !== false;
    var autoDef = (s.autoReconnect !== undefined) ? !!s.autoReconnect : (s.connectOnStart !== false);
    document.getElementById('f_auto_reconnect').checked = autoDef;
    document.getElementById('f_encrypted').checked = !!s.encrypted;
    document.getElementById('save_btn').textContent = 'Update Server';
    document.getElementById('cancel_edit_btn').style.display = 'inline-block';
    document.getElementById('f_host').focus();
    showAlert('Loaded server settings for ' + s.shortname + '. Renaming the short name on save migrates its notification history.');
  }} catch (e) {{
    alert('Failed to load server: ' + e);
  }}
}}

function resetForm() {{
  document.getElementById('form_heading').textContent = 'Add a Server';
  document.getElementById('serverForm').reset();
  document.getElementById('f_previous_shortname').value = '';
  document.getElementById('f_connect_on_start').checked = true;
  document.getElementById('f_auto_reconnect').checked = true;
  document.getElementById('save_btn').textContent = 'Save Server';
  document.getElementById('cancel_edit_btn').style.display = 'none';
  showAlert('Add server form reset.');
}}

async function saveServer(e) {{
  e.preventDefault();
  var payload = {{
    shortname: document.getElementById('f_shortname').value.trim(),
    previous_shortname: document.getElementById('f_previous_shortname').value.trim(),
    host: document.getElementById('f_host').value.trim(),
    tcpport: parseInt(document.getElementById('f_tcpport').value) || 10333,
    udpport: parseInt(document.getElementById('f_udpport').value) || 10333,
    username: document.getElementById('f_username').value.trim(),
    password: document.getElementById('f_password').value,
    nickname: document.getElementById('f_nickname').value.trim() || 'WebCom',
    status: document.getElementById('f_status').value.trim(),
    channel: document.getElementById('f_channel').value.trim() || '/text/',
    connectOnStart: document.getElementById('f_connect_on_start').checked,
    autoReconnect: document.getElementById('f_auto_reconnect').checked,
    encrypted: document.getElementById('f_encrypted').checked,
  }};

  try {{
    var res = await fetch('/servers', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    var data = await res.json();
    if (data.ok) {{
      showAlert('Server saved successfully.');
      setTimeout(function() {{ window.location.reload(); }}, 600);
    }} else {{
      alert('Error: ' + (data.error || 'Failed to save server'));
    }}
  }} catch (err) {{
    alert('Network error: ' + err);
  }}
}}

async function deleteServer(sn) {{
  if (!confirm('Are you sure you want to delete server ' + sn + '?')) return;
  try {{
    var res = await fetch('/servers', {{
      method: 'DELETE',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ shortname: sn }})
    }});
    var data = await res.json();
    if (data.ok) {{
      showAlert('Server ' + sn + ' deleted.');
      setTimeout(function() {{ window.location.reload(); }}, 600);
    }} else {{
      alert('Error: ' + (data.error || 'Failed to delete server'));
    }}
  }} catch (err) {{
    alert('Network error: ' + err);
  }}
}}

async function connectServer(sn) {{
  showAlert('Connecting to ' + sn + '...');
  try {{
    await fetch('/servers/connect/' + sn, {{ method: 'POST' }});
  }} catch (e) {{
    alert('Failed to connect: ' + e);
  }}
}}

async function disconnectServer(sn) {{
  showAlert('Disconnecting from ' + sn + '...');
  try {{
    await fetch('/servers/disconnect/' + sn, {{ method: 'POST' }});
  }} catch (e) {{
    alert('Failed to disconnect: ' + e);
  }}
}}
</script>
"""
    return _wrap("Servers", content, active="servers")


# ---------------------------------------------------------------------------
# Settings (includes per-server notification configuration)
# ---------------------------------------------------------------------------
def settings_html(servers: list[dict], defaults: dict | None = None) -> str:
    from .. import config_store
    defaults = defaults or {}
    defaults_json = json.dumps(defaults)

    def _on(val) -> bool:
        return val not in (None, False, 0, "0", "")

    rows = []
    for s in servers:
        sn = html.escape(s.get("shortname", ""))
        eff = config_store.effective_notify_settings(s, defaults)
        inherit = s.get("inheritNotifyDefaults", True)
        cells = ""
        for key in ("notifyloginout", "notifymessage", "systemnotify",
                    "ntfy", "prowl", "mgnotify", "pushover"):
            src = "server" if (not inherit and key in s) else "global"
            label = "Enabled" if _on(eff.get(key)) else "Disabled"
            src_span = ('<span class="muted" title="Set on this server only">(server)</span>'
                        if src == "server"
                        else '<span class="muted" title="Inherited from global defaults">(global)</span>')
            cells += f'<td>{label} {src_span}</td>'
        rows.append(
            f'<tr><td><strong>{sn}</strong></td>{cells}'
            f'<td><button type="button" onclick="loadServerNotifs(\'{sn}\')">Configure</button></td></tr>'
        )

    server_opts = "".join(f'<option value="{html.escape(s.get("shortname", ""))}">{html.escape(s.get("shortname", ""))}</option>' for s in servers)
    servers_json = json.dumps({s.get("shortname"): s for s in servers})

    content = f"""
<p>All WebCom settings live here. Notification behavior starts from the <strong>Global Defaults</strong> below; individual servers can then override anything they need to.</p>

<h2>Global Notification Defaults</h2>
<form id="defaultsForm" method="post" action="/settings" onsubmit="saveDefaults(event)">
  <fieldset>
    <legend>Event Triggers</legend>
    <div class="form-group">
      <label><input id="g_notifyloginout" type="checkbox" name="notifyloginout" value="1"> Notify when users log in or log out</label>
    </div>
    <div class="form-group">
      <label><input id="g_notifymessage" type="checkbox" name="notifymessage" value="1"> Notify on incoming channel and private messages</label>
    </div>
    <div class="form-group">
      <label><input id="g_systemnotify" type="checkbox" name="systemnotify" value="1"> Host system desktop notification</label>
    </div>
  </fieldset>

  <fieldset>
    <legend>ntfy Push Notifications</legend>
    <div class="form-group">
      <label><input id="g_ntfy" type="checkbox" name="ntfy" value="1"> Enable ntfy</label>
    </div>
    <div class="form-group">
      <label for="g_ntfyUrl">ntfy Server URL</label>
      <input id="g_ntfyUrl" name="ntfyUrl" placeholder="https://ntfy.sh">
    </div>
    <div class="form-group">
      <label for="g_ntfyTopic">ntfy Topic</label>
      <input id="g_ntfyTopic" name="ntfyTopic" placeholder="e.g. my-teamtalk-topic">
    </div>
    <div class="form-group">
      <label for="g_ntfyUser">ntfy Username (optional)</label>
      <input id="g_ntfyUser" name="ntfyUser">
    </div>
    <div class="form-group">
      <label for="g_ntfyPassword">ntfy Password (optional)</label>
      <input id="g_ntfyPassword" name="ntfyPassword" type="password">
    </div>
  </fieldset>

  <fieldset>
    <legend>Other Push Services</legend>
    <div class="form-group">
      <label><input id="g_prowl" type="checkbox" name="prowl" value="1"> Enable Prowl (iOS)</label>
    </div>
    <div class="form-group">
      <label for="g_prowlkey">Prowl API Key</label>
      <input id="g_prowlkey" name="prowlkey">
    </div>
    <div class="form-group">
      <label><input id="g_mgnotify" type="checkbox" name="mgnotify" value="1"> Enable MG Notify</label>
    </div>
    <div class="form-group">
      <label for="g_mgnotifykey">MG Notify API Key</label>
      <input id="g_mgnotifykey" name="mgnotifykey">
    </div>
    <div class="form-group">
      <label><input id="g_pushover" type="checkbox" name="pushover" value="1"> Enable Pushover</label>
    </div>
    <div class="form-group">
      <label for="g_pushoveruser">Pushover User Key</label>
      <input id="g_pushoveruser" name="pushoveruser">
    </div>
    <div class="form-group">
      <label for="g_pushovertoken">Pushover App Token</label>
      <input id="g_pushovertoken" name="pushovertoken">
    </div>
  </fieldset>

  <button type="submit" class="primary">Save Global Defaults</button>
</form>

<h2>Notification Preferences by Server</h2>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th scope="col">Server</th>
        <th scope="col">Login/Out</th>
        <th scope="col">Messages</th>
        <th scope="col">System</th>
        <th scope="col">ntfy</th>
        <th scope="col">Prowl</th>
        <th scope="col">MG Notify</th>
        <th scope="col">Pushover</th>
        <th scope="col">Action</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows) if rows else '<tr><td colspan="9">No servers configured.</td></tr>'}
    </tbody>
  </table>
  <p class="hint">The table shows each server's <em>effective</em> values. <strong>(global)</strong> means it inherits the Global Defaults; <strong>(server)</strong> means this server overrides them.</p>
</div>

<div id="notif_alert" role="status" aria-live="polite" class="status-message" style="display:none;"></div>

<h2>Configure Notifications for Server</h2>
<form id="notifForm" method="post" action="/settings" onsubmit="saveNotifs(event)">
  <div class="form-group">
    <label for="n_shortname">Select Server</label>
    <select id="n_shortname" name="shortname" onchange="loadServerNotifs(this.value)">
      {server_opts}
    </select>
  </div>

  <div class="form-group">
    <label><input id="n_inherit" name="inheritNotifyDefaults" type="checkbox" onchange="toggleInherit()"> Use global notification defaults for this server</label>
    <div class="hint">When checked, this server follows the Global Defaults above and its per-server settings below are ignored. Uncheck to override anything for this server only.</div>
  </div>

  <fieldset id="n_override_fields">
    <legend>Event Triggers</legend>
    <div class="form-group">
      <label><input id="n_notifyloginout" type="checkbox" name="notifyloginout" value="1"> Notify when users log in or log out</label>
    </div>
    <div class="form-group">
      <label><input id="n_notifymessage" type="checkbox" name="notifymessage" value="1"> Notify on incoming channel and private messages</label>
    </div>
    <div class="form-group">
      <label><input id="n_systemnotify" type="checkbox" name="systemnotify" value="1"> Host system desktop notification</label>
    </div>
  </fieldset>

  <fieldset>
    <legend>ntfy Push Notifications</legend>
    <div class="form-group">
      <label><input id="n_ntfy" type="checkbox" name="ntfy" value="1"> Enable ntfy</label>
    </div>
    <div class="form-group">
      <label for="n_ntfyUrl">ntfy Server URL</label>
      <input id="n_ntfyUrl" name="ntfyUrl" placeholder="https://ntfy.sh">
    </div>
    <div class="form-group">
      <label for="n_ntfyTopic">ntfy Topic</label>
      <input id="n_ntfyTopic" name="ntfyTopic" placeholder="e.g. my-teamtalk-topic">
    </div>
    <div class="form-group">
      <label for="n_ntfyUser">ntfy Username (optional)</label>
      <input id="n_ntfyUser" name="ntfyUser">
    </div>
    <div class="form-group">
      <label for="n_ntfyPassword">ntfy Password (optional)</label>
      <input id="n_ntfyPassword" name="ntfyPassword" type="password">
    </div>
  </fieldset>

  <fieldset>
    <legend>Other Push Services</legend>
    <div class="form-group">
      <label><input id="n_prowl" type="checkbox" name="prowl" value="1"> Enable Prowl (iOS)</label>
    </div>
    <div class="form-group">
      <label for="n_prowlkey">Prowl API Key</label>
      <input id="n_prowlkey" name="prowlkey">
    </div>
    <div class="form-group">
      <label><input id="n_mgnotify" type="checkbox" name="mgnotify" value="1"> Enable MG Notify</label>
    </div>
    <div class="form-group">
      <label for="n_mgnotifykey">MG Notify API Key</label>
      <input id="n_mgnotifykey" name="mgnotifykey">
    </div>
    <div class="form-group">
      <label><input id="n_pushover" type="checkbox" name="pushover" value="1"> Enable Pushover</label>
    </div>
    <div class="form-group">
      <label for="n_pushoveruser">Pushover User Key</label>
      <input id="n_pushoveruser" name="pushoveruser">
    </div>
    <div class="form-group">
      <label for="n_pushovertoken">Pushover App Token</label>
      <input id="n_pushovertoken" name="pushovertoken">
    </div>
  </fieldset>

  <p class="hint">Values you save here override the global defaults for <strong>this</strong> server only.</p>
  <button type="submit" class="primary">Save Settings for This Server</button>
</form>

<script>
var allServers = {servers_json};
var notifDefaults = {defaults_json};

function loadGlobalDefaults() {{
  var d = notifDefaults || {{}};
  document.getElementById('g_notifyloginout').checked = d.notifyloginout !== false && d.notifyloginout !== '0';
  document.getElementById('g_notifymessage').checked = d.notifymessage !== false && d.notifymessage !== '0';
  document.getElementById('g_systemnotify').checked = !!(d.systemnotify && d.systemnotify !== '0');
  document.getElementById('g_ntfy').checked = !!(d.ntfy && d.ntfy !== '0');
  document.getElementById('g_ntfyUrl').value = d.ntfyUrl || 'https://ntfy.sh';
  document.getElementById('g_ntfyTopic').value = d.ntfyTopic || '';
  document.getElementById('g_ntfyUser').value = d.ntfyUser || '';
  document.getElementById('g_ntfyPassword').value = d.ntfyPassword || '';
  document.getElementById('g_prowl').checked = !!(d.prowl && d.prowl !== '0');
  document.getElementById('g_prowlkey').value = d.prowlkey || '';
  document.getElementById('g_mgnotify').checked = !!(d.mgnotify && d.mgnotify !== '0');
  document.getElementById('g_mgnotifykey').value = d.mgnotifykey || '';
  document.getElementById('g_pushover').checked = !!(d.pushover && d.pushover !== '0');
  document.getElementById('g_pushoveruser').value = d.pushoveruser || '';
  document.getElementById('g_pushovertoken').value = d.pushovertoken || '';
}}

function testSummary(d) {{
  if (!d.test || !d.test.results || !d.test.results.length) return '';
  var res = d.test.results.join('; ');
  var scope = d.test.scope === 'global' ? 'globally' : ('on ' + d.test.scope);
  return ' We sent a test push notification to prove this works ' + scope + ': ' + res + '.';
}}

async function saveDefaults(e) {{
  e.preventDefault();
  var payload = {{
    notif_defaults: true,
    notifyloginout: document.getElementById('g_notifyloginout').checked ? '1' : '0',
    notifymessage: document.getElementById('g_notifymessage').checked ? '1' : '0',
    systemnotify: document.getElementById('g_systemnotify').checked ? '1' : '0',
    ntfy: document.getElementById('g_ntfy').checked ? '1' : '0',
    ntfyUrl: document.getElementById('g_ntfyUrl').value.trim(),
    ntfyTopic: document.getElementById('g_ntfyTopic').value.trim(),
    ntfyUser: document.getElementById('g_ntfyUser').value.trim(),
    ntfyPassword: document.getElementById('g_ntfyPassword').value,
    prowl: document.getElementById('g_prowl').checked ? '1' : '0',
    prowlkey: document.getElementById('g_prowlkey').value.trim(),
    mgnotify: document.getElementById('g_mgnotify').checked ? '1' : '0',
    mgnotifykey: document.getElementById('g_mgnotifykey').value.trim(),
    pushover: document.getElementById('g_pushover').checked ? '1' : '0',
    pushoveruser: document.getElementById('g_pushoveruser').value.trim(),
    pushovertoken: document.getElementById('g_pushovertoken').value.trim()
  }};
  try {{
    var res = await fetch('/settings', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    var d = await res.json();
    var alertDiv = document.getElementById('notif_alert');
    alertDiv.style.display = 'block';
    if (d.ok) {{
      alertDiv.textContent = 'Global defaults saved and applied to all servers. PowerCom config refreshed (no reconnect).' + testSummary(d);
      setTimeout(function() {{ window.location.reload(); }}, 1200);
    }} else {{
      alertDiv.textContent = 'Error saving global defaults';
    }}
  }} catch (err) {{
    alert('Network error: ' + err);
  }}
}}

function loadServerNotifs(sn) {{
  var s = allServers[sn] || {{}};
  var d = notifDefaults || {{}};
  var inherit = s.inheritNotifyDefaults !== false;
  var base = inherit ? d : s;
  var pick = function(k) {{ return base[k] !== undefined ? base[k] : d[k]; }};
  document.getElementById('n_shortname').value = sn;
  document.getElementById('n_inherit').checked = inherit;
  document.getElementById('n_notifyloginout').checked = pick('notifyloginout') !== false && pick('notifyloginout') !== '0';
  document.getElementById('n_notifymessage').checked = pick('notifymessage') !== false && pick('notifymessage') !== '0';
  document.getElementById('n_systemnotify').checked = !!(pick('systemnotify') && pick('systemnotify') !== '0');
  document.getElementById('n_ntfy').checked = !!(pick('ntfy') && pick('ntfy') !== '0');
  document.getElementById('n_ntfyUrl').value = pick('ntfyUrl') || 'https://ntfy.sh';
  document.getElementById('n_ntfyTopic').value = pick('ntfyTopic') || '';
  document.getElementById('n_ntfyUser').value = pick('ntfyUser') || '';
  document.getElementById('n_ntfyPassword').value = pick('ntfyPassword') || '';
  document.getElementById('n_prowl').checked = !!(pick('prowl') && pick('prowl') !== '0');
  document.getElementById('n_prowlkey').value = pick('prowlkey') || '';
  document.getElementById('n_mgnotify').checked = !!(pick('mgnotify') && pick('mgnotify') !== '0');
  document.getElementById('n_mgnotifykey').value = pick('mgnotifykey') || '';
  document.getElementById('n_pushover').checked = !!(pick('pushover') && pick('pushover') !== '0');
  document.getElementById('n_pushoveruser').value = pick('pushoveruser') || '';
  document.getElementById('n_pushovertoken').value = pick('pushovertoken') || '';
  toggleInherit();

  var alertDiv = document.getElementById('notif_alert');
  alertDiv.style.display = 'block';
  alertDiv.textContent = inherit
    ? ('Loaded ' + sn + ' (uses global defaults; per-server settings are disabled until you uncheck the box).')
    : ('Loaded ' + sn + ' with its own per-server settings.');
}}

function toggleInherit() {{
  var on = document.getElementById('n_inherit').checked;
  var form = document.getElementById('notifForm');
  var inputs = form.querySelectorAll('input, select, input, textarea');
  for (var i = 0; i < inputs.length; i++) {{
    var el = inputs[i];
    if (el.id === 'n_shortname' || el.id === 'n_inherit') continue;
    if (el.type === 'submit' || el.id === 'n_inherit') continue;
    el.disabled = on;
  }}
}}

var initialSn = document.getElementById('n_shortname').value;
if (initialSn) loadServerNotifs(initialSn);
loadGlobalDefaults();

async function saveNotifs(e) {{
  e.preventDefault();
  var payload = {{
    shortname: document.getElementById('n_shortname').value,
    inheritNotifyDefaults: document.getElementById('n_inherit').checked,
    notifyloginout: document.getElementById('n_notifyloginout').checked ? '1' : '0',
    notifymessage: document.getElementById('n_notifymessage').checked ? '1' : '0',
    systemnotify: document.getElementById('n_systemnotify').checked ? '1' : '0',
    ntfy: document.getElementById('n_ntfy').checked ? '1' : '0',
    ntfyUrl: document.getElementById('n_ntfyUrl').value.trim(),
    ntfyTopic: document.getElementById('n_ntfyTopic').value.trim(),
    ntfyUser: document.getElementById('n_ntfyUser').value.trim(),
    ntfyPassword: document.getElementById('n_ntfyPassword').value,
    prowl: document.getElementById('n_prowl').checked ? '1' : '0',
    prowlkey: document.getElementById('n_prowlkey').value.trim(),
    mgnotify: document.getElementById('n_mgnotify').checked ? '1' : '0',
    mgnotifykey: document.getElementById('n_mgnotifykey').value.trim(),
    pushover: document.getElementById('n_pushover').checked ? '1' : '0',
    pushoveruser: document.getElementById('n_pushoveruser').value.trim(),
    pushovertoken: document.getElementById('n_pushovertoken').value.trim()
  }};

  try {{
    var res = await fetch('/settings', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    var d = await res.json();
    if (d.ok) {{
      var alertDiv = document.getElementById('notif_alert');
      alertDiv.style.display = 'block';
      alertDiv.textContent = 'Settings saved for ' + payload.shortname + ' and applied. PowerCom config refreshed (no reconnect).' + testSummary(d);
      setTimeout(function() {{ window.location.reload(); }}, 1200);
    }} else {{
      alert('Error saving settings');
    }}
  }} catch (err) {{
    alert('Network error: ' + err);
  }}
}}
</script>
"""
    return _wrap("Settings", content, active="settings")


# ---------------------------------------------------------------------------
# Notifications (live server notification feed)
# ---------------------------------------------------------------------------
def notifications_html(servers: list[dict]) -> str:
    server_opts = "".join(f'<option value="{html.escape(s.get("shortname", ""))}">{html.escape(s.get("shortname", ""))}</option>' for s in servers)
    _KIND_OPTS = (
        ("", "All kinds"),
        ("pm", "Private messages"),
        ("channel", "Channel messages"),
        ("broadcast", "Broadcasts"),
        ("custom", "Custom messages"),
        ("login", "Logins"),
        ("logout", "Logouts"),
        ("kick", "Kicks"),
        ("status", "Status changes"),
        ("joined", "Users joined"),
        ("left", "Users left"),
        ("file", "File transfers"),
        ("system", "System / server"),
    )
    kind_opts = "".join(f'<option value="{k}">{label}</option>' for k, label in _KIND_OPTS)
    direction_opts = (
        '<option value="">All directions</option>'
        '<option value="in">Received</option>'
        '<option value="out">Sent (PMs)</option>'
    )

    content = f"""
<p>Notifications are stored in a local history database, so you can review past logins, logouts, and messages even if you were away. Filter by server, kind, or direction below. Outbound private messages are recorded as &ldquo;Sent&rdquo; PMs.</p>

<div class="actions-group" style="margin-bottom:.5rem;">
  <fieldset style="display:inline-flex;gap:.75rem;padding:.25rem .75rem;margin:0;align-items:center;">
    <legend>Filters</legend>
    <label>Server
      <select id="nf_server" onchange="loadHistory()">
        <option value="">All servers</option>
        {server_opts}
      </select>
    </label>
    <label>Kind
      <select id="nf_kind" onchange="loadHistory()">
        {kind_opts}
      </select>
    </label>
    <label>Direction
      <select id="nf_dir" onchange="loadHistory()">
        {direction_opts}
      </select>
    </label>
  </fieldset>
  <button type="button" onclick="loadHistory()">Refresh</button>
  <button type="button" onclick="markRead()">Mark all as read</button>
  <button type="button" onclick="clearHistory()">Clear history</button>
  <label><input type="checkbox" id="notif_pause" onchange="togglePause()"> Pause live updates</label>
</div>

<div id="notif_alert" role="status" aria-live="polite" class="status-message" style="display:none;">Loading notification history...</div>
<div id="notif_empty" class="status-message" style="display:none;">No notifications match the current filters.</div>

<ol id="notif_list"
    style="font-family:monospace;max-height:70vh;overflow-y:auto;padding:.75rem 1rem;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;list-style-type:none;margin:0;"
    aria-live="polite" aria-atomic="false"></ol>

<script>
var isPaused = false;
var es = new EventSource('/api/events');

function fServer() {{ return document.getElementById('nf_server').value; }}
function fKind() {{ return document.getElementById('nf_kind').value; }}
function fDir() {{ return document.getElementById('nf_dir').value; }}

function scopeObj() {{
  var s = {{}};
  if (fServer()) s.server = fServer();
  if (fKind()) s.kind = fKind();
  if (fDir()) s.direction = fDir();
  return s;
}}

function buildQuery() {{
  var s = scopeObj();
  var parts = [];
  if (s.server) parts.push('server=' + encodeURIComponent(s.server));
  if (s.kind) parts.push('kind=' + encodeURIComponent(s.kind));
  if (s.direction) parts.push('direction=' + encodeURIComponent(s.direction));
  parts.push('limit=500');
  return '/api/notifications?' + parts.join('&');
}}

function renderItem(n, fresh) {{
  var li = document.createElement('li');
  li.className = 'notif-item' + (fresh || !n.seen ? ' unread' : '');
  if (n.id != null) li.setAttribute('data-id', n.id);
  var seg = [];
  seg.push('[' + (n.readable_time || '') + ']');
  seg.push('[' + (n.server || '') + ':' + (n.kind || '') + ']');
  if (n.kind === 'pm' && n.direction) {{
    seg.push((n.direction === 'out' ? 'to ' : 'from ') + (n.peer || 'unknown'));
  }} else if (n.peer) {{
    seg.push(n.peer);
  }}
  li.appendChild(document.createTextNode(seg.join(' ')));
  if (n.text) {{
    li.appendChild(document.createTextNode(' — '));
    var txt = document.createElement('span');
    txt.textContent = n.text;
    li.appendChild(txt);
  }}
  return li;
}}

async function loadHistory() {{
  var alertDiv = document.getElementById('notif_alert');
  alertDiv.style.display = 'block';
  alertDiv.textContent = 'Loading notification history...';
  try {{
    var res = await fetch(buildQuery());
    var d = await res.json();
    if (!d.ok) throw new Error(d.error || 'Failed to load history');
    var box = document.getElementById('notif_list');
    box.innerHTML = '';
    (d.notifications || []).forEach(function(n) {{ box.appendChild(renderItem(n, false)); }});
    document.getElementById('notif_empty').style.display =
      (d.notifications || []).length ? 'none' : 'block';
    alertDiv.style.display = 'none';
    markRead();
  }} catch (err) {{
    alertDiv.textContent = 'History error: ' + err;
  }}
}}

async function markRead() {{
  try {{
    await fetch('/api/notifications/mark-read', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(scopeObj())
    }});
    var items = document.querySelectorAll('#notif_list .unread');
    for (var i = 0; i < items.length; i++) items[i].classList.remove('unread');
    if (window.refreshBadge) window.refreshBadge();
  }} catch (err) {{ console.error(err); }}
}}

async function clearHistory() {{
  if (!confirm('Permanently delete all notifications matching the current filters?')) return;
  try {{
    await fetch('/api/notifications/clear', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(scopeObj())
    }});
    loadHistory();
    if (window.refreshBadge) window.refreshBadge();
  }} catch (err) {{ alert('Clear failed: ' + err); }}
}}

es.onmessage = function(e) {{
  try {{
    var d = JSON.parse(e.data);
    if (d.type !== 'notification') return;
    if (fServer() && d.server !== fServer()) return;
    if (fKind() && d.kind !== fKind()) return;
    if (fDir() && d.direction !== fDir()) return;
    var box = document.getElementById('notif_list');
    box.insertBefore(renderItem(d, true), box.firstChild);
    document.getElementById('notif_empty').style.display = 'none';
    var alertDiv = document.getElementById('notif_alert');
    if (alertDiv.style.display !== 'none') {{ alertDiv.style.display = 'none'; }}
  }} catch (err) {{ console.error('Failed to parse event:', err); }}
}};

function togglePause() {{
  isPaused = document.getElementById('notif_pause').checked;
  var box = document.getElementById('notif_list');
  box.setAttribute('aria-live', isPaused ? 'off' : 'polite');
}}

loadHistory();
</script>
"""
    return _wrap("Notifications", content, active="notifications")


# ---------------------------------------------------------------------------
# Private Messages (Standard TeamTalk PM + TTCom PM)
# ---------------------------------------------------------------------------
def pmsg_html(servers: list[dict]) -> str:
    opts = "".join(f'<option value="{html.escape(s.get("shortname", ""))}">{html.escape(s.get("shortname", ""))}</option>' for s in servers)
    content = f"""
<p>Send direct private messages on TeamTalk. You can send a <strong>Standard TeamTalk PM</strong> (visible to desktop, mobile, and web clients) or a <strong>TTCom PM</strong> (hidden from standard clients, visible only to TTCom/WebCom).</p>

<p>First look up the recipient by typing all or part of their nickname or username, then pick the correct match from the dropdown. This is important when the same user is signed in more than once (for example with both a regular client and a Commander client).</p>

<form id="pmForm" onsubmit="return false;">
  <div class="form-group">
    <label for="pm_server">Server</label>
    <select id="pm_server" name="shortname">{opts}</select>
  </div>
  <fieldset>
    <legend>Message Type</legend>
    <div class="form-group">
      <label><input type="radio" name="pm_mode" value="standard" checked> Standard TeamTalk PM (visible to all users)</label>
    </div>
    <div class="form-group">
      <label><input type="radio" name="pm_mode" value="ttcom"> TTCom PM (invisible to normal desktop clients)</label>
    </div>
  </fieldset>
  <div class="form-group">
    <label for="pm_target">Look Up User (nickname, username, or #userid)</label>
    <div class="actions-group">
      <input id="pm_target" name="target" required placeholder="e.g. Alice" autocomplete="off">
      <button type="button" class="primary" onclick="findUsers()">Find User</button>
    </div>
  </div>
  <div class="form-group">
    <label for="pm_user_select">Select Recipient</label>
    <select id="pm_user_select" aria-describedby="pm_user_hint">
      <option value="">No user selected yet</option>
    </select>
    <div class="hint" id="pm_user_hint">If a name matches more than one user, all matches will appear here (e.g. the same person on a normal client and a Commander client). Pick the right one.</div>
  </div>
  <div class="form-group">
    <label for="pm_text">Message Text</label>
    <textarea id="pm_text" name="text" rows="3" required placeholder="Type your private message here..."></textarea>
  </div>
  <button type="submit" class="primary" onclick="sendPrivateMessage(event)">Send to Selected User</button>
</form>

<h2>Delivery Status</h2>
<div id="pm_output" role="status" aria-live="polite" class="status-message" style="display:none;"></div>

<h2>Message Inbox</h2>
<p>Received and sent private messages are stored in the local notification history. They show the recipient/sender as <em>nickname (username)</em> — the same person signed in twice shows two entries, so check the username when choosing who to reply to.</p>
<div class="actions-group" style="margin-bottom:.5rem;">
  <button type="button" onclick="loadInbox()">Refresh</button>
  <button type="button" onclick="clearInbox()">Clear PM history</button>
</div>
<div id="pm_inbox_empty" class="status-message" style="display:none;">No private messages recorded yet.</div>
<ol id="pm_inbox" style="font-family:monospace;max-height:45vh;overflow-y:auto;padding:.5rem 1rem;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;list-style-type:none;margin:0;" aria-live="polite"></ol>

<script>
async function findUsers() {{
  var sn = document.getElementById('pm_server').value;
  var tgt = document.getElementById('pm_target').value.trim();
  var select = document.getElementById('pm_user_select');
  var outBox = document.getElementById('pm_output');

  if (!tgt) {{
    alert('Type a nickname, username, or #userid to look up.');
    return;
  }}

  outBox.style.display = 'block';
  outBox.textContent = 'Looking up "' + tgt + '" on ' + sn + '...';

  try {{
    var res = await fetch('/api/users', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ shortname: sn, target: tgt }})
    }});
    var d = await res.json();
    if (!d.ok) throw new Error(d.error || 'Lookup failed');
    var users = d.users || [];
    select.innerHTML = '';
    if (users.length === 0) {{
      select.innerHTML = '<option value="">No matching users</option>';
      outBox.textContent = 'No users on ' + sn + ' matched "' + tgt + '".';
      return;
    }}
    users.forEach(function(u) {{
      var opt = document.createElement('option');
      opt.value = '#' + u.userid;
      var label = u.label || (u.nickname || (u.username || ('user #' + u.userid)));
      if (u.username && !u.label) label += ' (username: ' + u.username + ')';
      opt.textContent = label;
      select.appendChild(opt);
    }});
    outBox.textContent = 'Found ' + users.length + ' match' + (users.length > 1 ? 'es' : '') + '. Select the recipient, then press "Send to Selected User".';
    document.getElementById('pm_text').focus();
  }} catch (err) {{
    outBox.textContent = 'Lookup error: ' + err;
    select.innerHTML = '<option value="">No user selected yet</option>';
  }}
}}

async function sendPrivateMessage(e) {{
  e.preventDefault();
  var sn = document.getElementById('pm_server').value;
  var uid = document.getElementById('pm_user_select').value;
  var txt = document.getElementById('pm_text').value.trim();
  var isTTCom = document.querySelector('input[name="pm_mode"]:checked').value === 'ttcom';
  var outBox = document.getElementById('pm_output');

  if (!uid) {{
    alert('Click "Find User" and pick a recipient from the dropdown first.');
    return;
  }}
  if (!txt) return;

  outBox.style.display = 'block';
  outBox.textContent = 'Sending message to ' + uid + '...';

  try {{
    var res = await fetch('/pmsg', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        shortname: sn,
        target: uid,
        text: txt,
        is_ttcom: isTTCom
      }})
    }});
    var d = await res.json();
    if (d.ok) {{
      var lines = Array.isArray(d.output) ? d.output.join('\\n') : (d.output || 'Message sent.');
      outBox.textContent = lines || 'Message sent to ' + uid + '.';
      document.getElementById('pm_text').value = '';
      loadInbox();
    }} else {{
      outBox.textContent = 'Error: ' + (d.error || 'Failed to send message');
    }}
  }} catch (err) {{
    outBox.textContent = 'Network error: ' + err;
  }}
}}

function renderInboxItem(n, fresh) {{
  var li = document.createElement('li');
  li.className = 'notif-item' + (fresh || !n.seen ? ' unread' : '');
  var seg = [];
  seg.push('[' + (n.readable_time || '') + ']');
  if (n.kind === 'pm' && n.direction) {{
    seg.push((n.direction === 'out' ? 'to ' : 'from ') + (n.peer || 'unknown'));
  }}
  li.appendChild(document.createTextNode(seg.join(' ')));
  if (n.text) {{
    li.appendChild(document.createTextNode(' — '));
    var txt = document.createElement('span');
    txt.textContent = n.text;
    li.appendChild(txt);
  }}
  return li;
}}

async function loadInbox() {{
  try {{
    var res = await fetch('/api/notifications?kind=pm&limit=300');
    var d = await res.json();
    var box = document.getElementById('pm_inbox');
    box.innerHTML = '';
    (d.notifications || []).forEach(function(n) {{ box.appendChild(renderInboxItem(n, false)); }});
    document.getElementById('pm_inbox_empty').style.display =
      (d.notifications || []).length ? 'none' : 'block';
  }} catch (err) {{ console.error('Inbox error:', err); }}
}}

async function clearInbox() {{
  if (!confirm('Permanently delete all recorded private messages?')) return;
  try {{
    await fetch('/api/notifications/clear', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ kind: 'pm' }})
    }});
    loadInbox();
  }} catch (err) {{ alert('Clear failed: ' + err); }}
}}

var es = new EventSource('/api/events');
es.onmessage = function(e) {{
  try {{
    var d = JSON.parse(e.data);
    if (d.type !== 'notification' || d.kind !== 'pm') return;
    var box = document.getElementById('pm_inbox');
    box.insertBefore(renderInboxItem(d, true), box.firstChild);
    document.getElementById('pm_inbox_empty').style.display = 'none';
    if (window.refreshBadge) window.refreshBadge();
  }} catch (err) {{ console.error('Failed to parse event:', err); }}
}};

loadInbox();
</script>
"""
    return _wrap("Private Messages", content, active="pmsg")


# ---------------------------------------------------------------------------
# Admin Console
# ---------------------------------------------------------------------------
def admin_html(servers: list[dict]) -> str:
    opts = "".join(f'<option value="{html.escape(s.get("shortname", ""))}">{html.escape(s.get("shortname", ""))}</option>' for s in servers)
    content = f"""
<p>Run TeamTalk administrator commands. Your user must hold the appropriate server rights (e.g. Kick, Ban, Broadcast) for administrative operations.</p>

<form id="adminForm" onsubmit="runAdminCommand(event)">
  <div class="form-group">
    <label for="admin_server">Target Server</label>
    <select id="admin_server" name="shortname">{opts}</select>
  </div>
  <div class="form-group">
    <label for="admin_cmd">Command</label>
    <input id="admin_cmd" name="command" required autocomplete="off"
           placeholder="e.g. kick username, ban list, broadcast Maintenance in 5m">
  </div>
  <button type="submit" class="primary">Execute Command</button>
</form>

<div style="margin: 1rem 0;">
  <p><strong>Quick Commands:</strong></p>
  <div class="actions-group">
    <button type="button" onclick="setAndRun('summary -a')">User Summary</button>
    <button type="button" onclick="setAndRun('channel list')">List Channels</button>
    <button type="button" onclick="setAndRun('stats')">Server Statistics</button>
    <button type="button" onclick="setAndRun('ban list')">List Bans</button>
    <button type="button" onclick="setAndRun('admins')">List Admins</button>
    <button type="button" onclick="setAndRun('ping')">Server Ping</button>
  </div>
</div>

<h2>Command Output</h2>
<pre id="admin_output" tabindex="0" role="region" aria-live="polite" aria-label="Command execution output"
     style="white-space:pre-wrap;font-family:monospace;max-height:45vh;overflow:auto;padding:.75rem 1rem;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;">No command executed yet.</pre>

<h2>Command Reference</h2>
<ul>
  <li><code>kick &lt;user&gt;</code> - Kick user from server</li>
  <li><code>ckick &lt;user&gt;</code> - Kick user from current channel</li>
  <li><code>kb &lt;user&gt;</code> - Kickban (kick from server and ban)</li>
  <li><code>ban list</code> - List active server bans</li>
  <li><code>ban add user=&lt;name&gt;</code> - Add ban by username/IP</li>
  <li><code>broadcast &lt;message&gt;</code> - Send server-wide broadcast announcement</li>
  <li><code>move &lt;user&gt; &lt;channel&gt;</code> - Move user to specified channel</li>
  <li><code>op &lt;user&gt;</code> - Grant operator rights to user in current channel</li>
  <li><code>whois &lt;user&gt;</code> - Look up detailed user account information</li>
  <li><code>geolocate &lt;user|ip&gt;</code> - IP geolocation lookup</li>
  <li><code>channel list</code> / <code>channel create ...</code> - Channel management</li>
</ul>

<script>
function setAndRun(cmd) {{
  document.getElementById('admin_cmd').value = cmd;
  executeCommand(cmd);
}}

function runAdminCommand(e) {{
  e.preventDefault();
  var cmd = document.getElementById('admin_cmd').value.trim();
  if (cmd) executeCommand(cmd);
}}

async function executeCommand(cmd) {{
  var sn = document.getElementById('admin_server').value;
  var outBox = document.getElementById('admin_output');
  outBox.textContent = 'Running: ' + cmd + '...';

  try {{
    var res = await fetch('/admin', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ shortname: sn, command: cmd }})
    }});
    var d = await res.json();
    if (d.needs_selection) {{
      renderSelection(d);
      return;
    }}
    if (d.ok) {{
      var lines = Array.isArray(d.output) ? d.output.join('\\n') : (d.output || 'Command completed.');
      outBox.textContent = lines || 'Command executed with no output.';
    }} else {{
      outBox.textContent = 'Error: ' + (d.error || 'Failed to execute command');
    }}
  }} catch (err) {{
    outBox.textContent = 'Network error: ' + err;
  }}
}}

function renderSelection(d) {{
  var outBox = document.getElementById('admin_output');
  outBox.textContent = 'Multiple users on this server match "' + d.token + '" — pick one:';
  d.matches.forEach(function(m, i) {{
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = (i + 1) + '. ' + m.label;
    btn.style.margin = '.25rem .25rem .25rem 0';
    btn.onclick = function() {{ runSelected(d, m.userid); }};
    outBox.appendChild(btn);
  }});
}}

async function runSelected(d, userid) {{
  var sn = document.getElementById('admin_server').value;
  var outBox = document.getElementById('admin_output');
  outBox.textContent = 'Running: ' + d.command + ' (user #' + userid + ')...';

  try {{
    var res = await fetch('/admin', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        shortname: sn,
        command: d.command,
        replace_index: d.user_index,
        userid: userid
      }})
    }});
    var r = await res.json();
    if (r.needs_selection) {{
      renderSelection(r);
      return;
    }}
    if (r.ok) {{
      var lines = Array.isArray(r.output) ? r.output.join('\\n') : (r.output || 'Command completed.');
      outBox.textContent = lines || 'Command executed with no output.';
    }} else {{
      outBox.textContent = 'Error: ' + (r.error || 'Failed to execute command');
    }}
  }} catch (err) {{
    outBox.textContent = 'Network error: ' + err;
  }}
}}
</script>
"""
    return _wrap("Admin Console", content, active="admin")


# ---------------------------------------------------------------------------
# Logs Page
# ---------------------------------------------------------------------------
def logs_html() -> str:
    content = """
<p>Live application and TeamTalk bridge logs. Auto-refresh is turned off by default for a comfortable screen-reader experience.</p>

<div class="actions-group" style="margin-bottom:1rem;">
  <button type="button" class="primary" onclick="loadLogs()">Refresh Logs</button>
  <label><input type="checkbox" id="auto_refresh" onchange="toggleAutoRefresh()"> Auto-refresh every 5 seconds</label>
  <button type="button" onclick="clearLogsView()">Clear View</button>
</div>

<div id="logs_status" role="status" aria-live="polite" class="status-message" style="display:none;"></div>

<pre id="logs" tabindex="0" role="region" aria-label="Application log contents"
     style="white-space:pre-wrap;font-family:monospace;max-height:65vh;overflow:auto;padding:1rem;background:#1e1e1e;color:#d4d4d4;border-radius:4px;border:1px solid var(--border);">
Loading logs...
</pre>

<script>
var timer = null;

async function loadLogs() {{
  try {{
    const r = await fetch('/api/logs');
    const d = await r.json();
    document.getElementById('logs').textContent = d.logs || 'No logs available';
    var st = document.getElementById('logs_status');
    st.style.display = 'block';
    st.textContent = 'Logs refreshed.';
    setTimeout(function() {{ st.style.display = 'none'; }}, 2000);
  }} catch (e) {{
    document.getElementById('logs').textContent = 'Failed to load logs: ' + e;
  }}
}}

function toggleAutoRefresh() {{
  var checked = document.getElementById('auto_refresh').checked;
  if (timer) clearInterval(timer);
  if (checked) {{
    timer = setInterval(loadLogs, 5000);
    document.getElementById('logs_status').style.display = 'block';
    document.getElementById('logs_status').textContent = 'Auto-refresh enabled (every 5 seconds).';
  }} else {{
    document.getElementById('logs_status').style.display = 'block';
    document.getElementById('logs_status').textContent = 'Auto-refresh disabled.';
  }}
}}

function clearLogsView() {{
  document.getElementById('logs').textContent = 'Log view cleared.';
}}

loadLogs();
</script>
"""
    return _wrap("Application Logs", content, active="logs")


# ---------------------------------------------------------------------------
# Users (whole-server roster)
# ---------------------------------------------------------------------------
def users_html(servers: list[dict]) -> str:
    server_opts = "".join(f'<option value="{html.escape(s.get("shortname", ""))}">{html.escape(s.get("shortname", ""))}</option>' for s in servers)

    content = f"""
<p>Whole-server roster: everyone connected right now (not just the current channel). TeamTalk user IDs change on every login, so identity is shown as <code>nickname (username)</code>.</p>

<div class="actions-group" style="margin-bottom:.5rem;">
  <fieldset style="display:inline-flex;gap:.75rem;padding:.25rem .75rem;margin:0;align-items:center;">
    <legend>View</legend>
    <label>Server
      <select id="roster_server" onchange="loadRoster()">
        {server_opts}
      </select>
    </label>
    <label>Filter <input type="search" id="roster_filter" placeholder="filter by name / user" oninput="renderRows()"></label>
  </fieldset>
  <button type="button" onclick="loadRoster()">Refresh</button>
  <label><input type="checkbox" id="roster_auto" checked onchange="toggleAuto()"> Auto-refresh (10s)</label>
</div>

<div id="roster_status" role="status" aria-live="polite" class="status-message" style="display:none;">Loading roster...</div>
<div id="roster_empty" class="status-message" style="display:none;">No users connected to this server.</div>

<table id="roster_table" style="width:100%;border-collapse:collapse;font-size:.9rem;">
  <thead>
    <tr>
      <th scope="col" style="text-align:left;">User</th>
      <th scope="col" style="text-align:left;">Username</th>
      <th scope="col" style="text-align:left;">ID</th>
      <th scope="col" style="text-align:left;">Type</th>
      <th scope="col" style="text-align:left;">Channel</th>
      <th scope="col" style="text-align:left;">Status</th>
      <th scope="col" style="text-align:left;">Client</th>
      <th scope="col" style="text-align:left;">IP</th>
    </tr>
  </thead>
  <tbody id="roster_body"></tbody>
</table>

<script>
var rosterData = {{ users: [], me: '' }};
var rosterTimer = null;
var es = new EventSource('/api/events');

function curServer() {{ return document.getElementById('roster_server').value; }}

function loadRoster() {{
  var st = document.getElementById('roster_status');
  st.style.display = 'block';
  st.textContent = 'Loading roster...';
  fetch('/api/users/roster?server=' + encodeURIComponent(curServer()))
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      if (!d.ok) throw new Error(d.error || 'Failed to load roster');
      rosterData = d.roster || {{ users: [], me: null }};
      renderRows();
      st.style.display = 'none';
    }})
    .catch(function(err) {{
      st.style.display = 'block';
      st.textContent = 'Roster error: ' + err;
    }});
}}

function esc(v) {{
  var out = document.createElement('span');
  out.textContent = v == null ? '' : String(v);
  return out.innerHTML;
}}

function renderRows() {{
  var body = document.getElementById('roster_body');
  body.innerHTML = '';
  var filter = (document.getElementById('roster_filter').value || '').toLowerCase();
  var rows = [];
  (rosterData.users || []).forEach(function(u) {{
    if (filter && (u.label || '').toLowerCase().indexOf(filter) === -1 &&
        (u.username || '').toLowerCase().indexOf(filter) === -1 &&
        (u.nickname || '').toLowerCase().indexOf(filter) === -1) return;
    rows.push('<tr>' +
      '<td>' + esc(u.label) + (u.me ? ' <span title="you">(me)</span>' : '') + '</td>' +
      '<td>' + esc(u.username) + '</td>' +
      '<td>' + esc(u.userid) + '</td>' +
      '<td>' + (u.admin ? 'Admin' : 'User') + '</td>' +
      '<td>' + esc(u.channel) + '</td>' +
      '<td>' + esc(u.statusmode) + ((u.statusmsg ? ' &mdash; ' + esc(u.statusmsg) : '')) + '</td>' +
      '<td>' + esc(u.clientname) + '</td>' +
      '<td>' + esc(u.ipaddr) + '</td>' +
      '</tr>');
  }});
  body.innerHTML = rows.join('');
  document.getElementById('roster_empty').style.display = rows.length ? 'none' : 'block';
}}

function toggleAuto() {{
  if (rosterTimer) clearInterval(rosterTimer);
  if (document.getElementById('roster_auto').checked) rosterTimer = setInterval(loadRoster, 10000);
}}

function refreshSoon() {{
  if (!document.getElementById('roster_auto').checked) return;
  if (rosterTimer) clearInterval(rosterTimer);
  loadRoster();
  rosterTimer = setInterval(loadRoster, 10000);
}}

es.onmessage = function(e) {{
  try {{
    var d = JSON.parse(e.data);
    if (d.type !== 'notification') return;
    var kinds = {{ login:1, logout:1, joined:1, left:1, status:1, kick:1 }};
    if (kinds[d.kind]) refreshSoon();
  }} catch (err) {{ /* ignore malformed events */ }}
}};

loadRoster();
if (document.getElementById('roster_auto').checked) rosterTimer = setInterval(loadRoster, 10000);
</script>
"""
    return _wrap("Users", content, active="users")
