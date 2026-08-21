"""WebCom page templates (server-rendered, screen-reader friendly).

Design notes for accessibility (per owner's requirements):
- Every interactive control has a <label>.
- The live event stream uses an ARIA live region (aria-live="polite") so
  screen readers announce new TT events (joins, PMs, kicks) as they arrive.
- Headings are used to structure pages; no spatial/visual-only cues.
- Forms post and the page re-renders with results announced via the live region.
"""

BASE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WebCom - {title}</title>
<a href="#main" style="position:absolute;left:-9999px">Skip to content</a>
<nav aria-label="Primary">
  <a href="/">Dashboard</a> |
  <a href="/servers">Servers</a> |
  <a href="/notifications">Notifications</a> |
  <a href="/logs">Logs</a> |
  <a href="/pmsg">TTCom PM</a> |
  <a href="/admin">Admin</a> |
  <a href="/logout">Logout</a>
</nav>
<main id="main">
<h1>WebCom - {title}</h1>
{content}
</main>
"""


def _wrap(title, content):
    return BASE.format(title=title, content=content)


def setup_html():
    return _wrap("Setup", """
<p>Welcome to WebCom. This wizard sets up the dashboard and your TeamTalk servers.</p>
<form method="post" id="wizard">
<h2>Step 1: Dashboard login</h2>
<p><label for="web_user">Dashboard username</label>
<input id="web_user" name="web_user" value="admin"></p>
<p><label for="web_pass">Dashboard password</label>
<input id="web_pass" name="web_pass" type="password" required></p>

<h2>Step 2: TeamTalk servers</h2>
<p>Add one or more servers. TeamTalk stores passwords in plaintext by design, so
they are kept only in the local data volume, never committed.</p>
<div id="servers"></div>
<button type="button" onclick="addServer()">Add another server</button>
<script>
function addServer(){
  var n=document.querySelectorAll('.srv').length;
  var d=document.createElement('div'); d.className='srv';
  d.innerHTML='<fieldset><legend>Server '+(n+1)+'</legend>'+
  '<label>Short name <input name="sn" required></label><br>'+
  '<label>Host <input name="host" required></label><br>'+
  '<label>TCP port <input name="tcpport" value="10333"></label><br>'+
  '<label>UDP port <input name="udpport" value="10333"></label><br>'+
  '<label>Username <input name="username"></label><br>'+
  '<label>Password <input name="password" type="password"></label><br>'+
  '<label>Nickname <input name="nickname" value="WebCom"></label><br>'+
  '<label>Status message <input name="status"></label><br>'+
  '<label>Channel to join (e.g. /text/) <input name="channel" value="/text/"></label><br>'+
  '<label>Encrypted <input type="checkbox" name="encrypted" value="1"></label><br>'+
  '</fieldset>';
  document.getElementById('servers').appendChild(d);
}
addServer();
</script>

<h2>Step 3: Finish</h2>
<button type="button" onclick="collect()">Save and start</button>
<script>
function collect(){
  var servers=[];
  document.querySelectorAll('.srv').forEach(function(s){
    servers.push({
      shortname:s.querySelector('[name=sn]').value,
      host:s.querySelector('[name=host]').value,
      tcpport:parseInt(s.querySelector('[name=tcpport]').value)||10333,
      udpport:parseInt(s.querySelector('[name=udpport]').value)||10333,
      username:s.querySelector('[name=username]').value,
      password:s.querySelector('[name=password]').value,
      nickname:s.querySelector('[name=nickname]').value,
      status:s.querySelector('[name=status]').value,
      channel:s.querySelector('[name=channel]').value,
      encrypted:s.querySelector('[name=encrypted]').checked,
      autoLogin:1
    });
  });
  var f=document.getElementById('wizard');
  var inp=document.createElement('input'); inp.type='hidden';
  inp.name='servers_json'; inp.value=JSON.stringify(servers);
  f.appendChild(inp); f.submit();
}
</script>
</form>
""")


def dashboard_html():
    return _wrap("Dashboard", """
<div aria-live="polite" id="events" style="white-space:pre-wrap;font-family:monospace;max-height:60vh;overflow:auto"></div>
<script>
var es=new EventSource('/api/events');
es.onmessage=function(e){
  var d=JSON.parse(e.data);
  var line='['+d.type+'] '+d.text;
  var box=document.getElementById('events');
  box.textContent+=line+'\\n'; box.scrollTop=box.scrollHeight;
};
</script>
""")


def servers_html(servers):
    rows = "".join(
        f"<li>{s.get('shortname')} - {s.get('host')}:{s.get('tcpport')} "
        f"(user {s.get('username')}) "
        f'<button type="button" onclick="editServer(\'{s.get("shortname")}\')">Edit</button></li>' for s in servers)
    return _wrap("Servers", f"""
<ul>{rows or '<li>No servers configured.</li>'}</ul>
<h2>Add / edit a server</h2>
<form id="serverForm" method="post" action="/servers">
<input type="hidden" name="shortname" id="f_shortname">
<p><label>Short name <input name="shortname" id="f_shortname_display" required></label></p>
<p><label>Host <input name="host" id="f_host" required></label></p>
<p><label>TCP port <input name="tcpport" id="f_tcpport" value="10333"></label></p>
<p><label>UDP port <input name="udpport" id="f_udpport" value="10333"></label></p>
<p><label>Username <input name="username" id="f_username"></label></p>
<p><label>Password <input name="password" id="f_password" type="password" autocomplete="new-password"></label></p>
<p><label>Nickname <input name="nickname" id="f_nickname" value="WebCom"></label></p>
<p><label>Status <input name="status" id="f_status"></label></p>
<p><label>Channel to join (e.g. /text/) <input name="channel" id="f_channel" value="/text/"></label></p>
<p><label>Encrypted <input name="encrypted" id="f_encrypted" type="checkbox" value="1"></label></p>
<button type="submit">Save server</button>
</form>
<script>
async function editServer(sn) {{
  const r = await fetch('/servers/edit/' + sn);
  const d = await r.json();
  if (!d.ok) return alert(d.error);
  const s = d.server;
  document.getElementById('f_shortname').value = s.shortname;
  document.getElementById('f_shortname_display').value = s.shortname;
  document.getElementById('f_host').value = s.host;
  document.getElementById('f_tcpport').value = s.tcpport;
  document.getElementById('f_udpport').value = s.udpport;
  document.getElementById('f_username').value = s.username || '';
  document.getElementById('f_password').value = s.password || '';
  document.getElementById('f_nickname').value = s.nickname || 'WebCom';
  document.getElementById('f_status').value = s.status || '';
  document.getElementById('f_channel').value = s.channel || '/text/';
  document.getElementById('f_encrypted').checked = s.encrypted || false;
}}
</script>
""")


def notifications_html(servers):
    items = "".join(
        f"<li>{s.get('shortname')}: "
        f"loginout={'✓' if s.get('notifyloginout', True) else '✗'} "
        f"message={'✓' if s.get('notifymessage', True) else '✗'} "
        f"system={'✓' if s.get('systemnotify', False) else '✗'} "
        f"ntfy={'✓' if s.get('ntfy', False) else '✗'} "
        f"ntfyUrl={s.get('ntfyUrl', '')} "
        f"ntfyTopic={s.get('ntfyTopic', '')} "
        f"prowl={'✓' if s.get('prowl', False) else '✗'} "
        f"mgnotify={'✓' if s.get('mgnotify', False) else '✗'} "
        f"pushover={'✓' if s.get('pushover', False) else '✗'}</li>"
        for s in servers)
    return _wrap("Notifications", f"""
<ul>{items or '<li>No servers.</li>'}</ul>
<h2>Toggle notifications for a server</h2>
<form method="post" action="/notifications">
<p><label>Server short name <input name="shortname" required></label></p>
<p><label>Notify login/out <input type="checkbox" name="notifyloginout" value="1"></label></p>
<p><label>Notify messages <input type="checkbox" name="notifymessage" value="1"></label></p>
<p><label>System notification <input type="checkbox" name="systemnotify" value="1"></label></p>
<p><label>ntfy <input type="checkbox" name="ntfy" value="1"></label></p>
<p><label>ntfy URL <input name="ntfyUrl" placeholder="https://ntfy.sh"></label></p>
<p><label>ntfy Topic <input name="ntfyTopic" placeholder="my-topic"></label></p>
<p><label>ntfy User <input name="ntfyUser"></label></p>
<p><label>ntfy Password <input name="ntfyPassword" type="password"></label></p>
<p><label>Prowl <input type="checkbox" name="prowl" value="1"></label></p>
<p><label>MG Notify <input type="checkbox" name="mgnotify" value="1"></label></p>
<p><label>Pushover <input type="checkbox" name="pushover" value="1"></label></p>
<button>Save</button>
</form>
""")


def logs_html():
    return _wrap("Logs", """
<div id="logs" style="white-space:pre-wrap;font-family:monospace;max-height:70vh;overflow:auto;background:#1e1e1e;color:#d4d4d4;padding:1rem;border-radius:4px">
Loading logs...
</div>
<script>
async function loadLogs() {
  try {
    const r = await fetch('/api/logs');
    const d = await r.json();
    document.getElementById('logs').textContent = d.logs || 'No logs available';
  } catch (e) {
    document.getElementById('logs').textContent = 'Failed to load logs: ' + e;
  }
}
loadLogs();
setInterval(loadLogs, 5000);
</script>
""")


def pmsg_html(servers):
    opts = "".join(f'<option value="{s.get("shortname")}">{s.get("shortname")}</option>' for s in servers)
    return _wrap("TTCom PM", f"""
<p>TTCom private messages are invisible to normal desktop TeamTalk clients.
They use the =sender= format and only TTCom-aware clients (like WebCom) see them.</p>
<form id="f">
<p><label for="sn">Server</label> <select id="sn" name="shortname">{opts}</select></p>
<p><label for="tgt">Target user</label> <input id="tgt" name="target"></p>
<p><label for="txt">Message</label> <textarea id="txt" name="text"></textarea></p>
<button type="button" onclick="send()">Send TTCom PM</button>
</form>
<pre id="out" aria-live="polite"></pre>
<script>
function send(){{
  fetch('/pmsg',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{shortname:sn.value,target:tgt.value,text:txt.value}})}})
    .then(r=>r.json()).then(d=>{{out.textContent=JSON.stringify(d.output);}});
}}
</script>
""")


def admin_html(servers):
    opts = "".join(f'<option value="{s.get("shortname")}">{s.get("shortname")}</option>' for s in servers)
    return _wrap("Admin", f"""
<p>Run TeamTalk administrator commands. These mirror TTComCmd's command set;
the server enforces its own rights (Ban/Kick/Broadcast).</p>
<form id="f">
<p><label for="sn">Server</label> <select id="sn" name="shortname">{opts}</select></p>
<p><label for="cmd">Command</label>
<input id="cmd" name="command" size="60" placeholder="kick bob  |  ckick -c bob  |  kb bob  |  ban list  |  ban add user=bob  |  broadcast Server down in 5m"></p>
<button type="button" onclick="run()">Run</button>
</form>
<pre id="out" aria-live="polite"></pre>
<script>
function run(){{
  fetch('/admin',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{shortname:sn.value,command:cmd.value}})}})
    .then(r=>r.json()).then(d=>{{out.textContent=JSON.stringify(d.output);}});
}}
</script>
<h2>Command reference</h2>
<ul>
<li><code>kick &lt;user&gt;</code> - kick from server</li>
<li><code>ckick &lt;user&gt;</code> / <code>kick -c &lt;user&gt;</code> - kick from channel</li>
<li><code>kb &lt;user&gt;</code> - kickban (kick + ban)</li>
<li><code>ban list</code> / <code>ban add user=&lt;name&gt;</code> / <code>ban delete ...</code> - ban management</li>
<li><code>broadcast &lt;msg&gt;</code> - server-wide message (needs Broadcast right)</li>
<li><code>move &lt;user&gt; &lt;channel&gt;</code> - move user to channel</li>
<li><code>op &lt;user&gt;</code> - op a user</li>
<li><code>geolocate &lt;user|ip&gt;</code> - IP geolocation</li>
<li><code>whoIs &lt;user&gt;</code>, <code>account list/add/delete</code>, <code>channel list</code>, <code>file get/delete</code></li>
</ul>
""")
