# WebCom

WebCom is a headless TeamTalk text client delivered as an accessible web dashboard. Based on PowerCom (a fork of TeamTalk Commander / TTCom by Doug Lee).

## Features

- **Web Dashboard** - Access and control TeamTalk from any browser
- **Multi-server support** - Connect to multiple TeamTalk servers side by side
- **Real-time event stream** - Live updates via Server-Sent Events (SSE)
- **Notification history** - Every login, logout, message, kick, and status change is stored in a local SQLite database and browsable with server/kind/direction filters
- **Private Message Inbox** - Sent and received PMs recorded as `nickname (username)`, with live updates
- **Unread badge** - Nav shows how many notifications are unread; mark-all-read on the notifications page
- **Ambiguous user handling** - If a name matches more than one user, WebCom lists the matches and asks you to pick (mirroring PowerCom's interactive 1/2/3 picker) instead of failing silently
- **Users page** - Whole-server roster (not just the current channel) showing nickname/(username)/user type/channel/status/client/IP, with live auto-refresh
- **Stable identities** - TeamTalk user IDs change every login, so all history and rosters use clean `nickname (username)` labels; stale `User <id>` rows are repaired automatically from the live roster
- **TTCom Private Messages** - Invisible to standard desktop clients, via the Find User flow
- **Admin commands** - Kick, ban, broadcast, move users, op, geolocate, etc.
- **Notifications** - ntfy, Prowl, Pushover, MG Notify, and system notification delivery (per-server, on `/settings`)
- **Logs page** - Real-time application logs in the browser
- **Server management** - Add/edit/remove servers via the UI

## Quick Start

### Prerequisites

- Docker & Docker Compose
- TeamTalk server(s) with credentials

### Deployment

```bash
# Clone the repository
git clone https://github.com/averlice/webcom.git
cd webcom

# Start the container
docker compose up -d

# View logs
docker compose logs -f webcom
```

The dashboard will be available at:

- **Local**: http://localhost:2032
- **Network**: http://YOUR_SERVER_IP:2032

### First Run Setup

1. Open the dashboard URL
2. You'll be redirected to the setup wizard (`/setup`)
3. Create a web dashboard admin user (argon2-hashed password)
4. Add TeamTalk server(s):
   - **Short name**: Unique identifier (e.g., `tunmi13`)
   - **Host**: TeamTalk server hostname (e.g., `tunmi13.com`)
   - **TCP/UDP Port**: Usually `10333` or `9483`
   - **Username/Password**: TeamTalk credentials (plaintext - TeamTalk protocol requirement)
   - **Nickname**: Display name in TeamTalk
   - **Channel**: Auto-join channel (e.g., `/text/`)
   - **Encrypted**: Enable if server uses TLS
5. Save and login

## Configuration

All persistent data lives in the `./data` volume (gitignored):

```
data/
├── config.local.json    # WebCom config (web admin hash, session secret, TT servers)
├── ttcom.conf           # Generated PowerCom config (auto-generated)
└── webcom.db            # SQLite notification / PM history
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBCOM_DATA_DIR` | `/data` | Data volume path |
| `WEBCOM_PORT` | `2032` | HTTP port |
| `WEBCOM_BIND` | `0.0.0.0` | Bind address |

### Security Notes

- **TeamTalk passwords** are stored in plaintext in `config.local.json` - this is a TeamTalk protocol requirement, not our choice (bearware documents it; the login protocol transmits the account password as-is). They exist **only** in the `/data` volume, never in the repo or the image.
- **Web dashboard passwords** are argon2-hashed; stored in `config.local.json` as `admin_hash`. The raw web password is never stored.
- **Never commit** `data/`, `tor-data/`, `uv.lock`, `ttcom.conf`, or `config.local.json`. The `.gitignore` and `.dockerignore` already exclude them so they can't leak through a careless `git add .` or a container build.
- Session cookies are signed with a random secret generated at setup (`session_secret` in `config.local.json`), so cookies can't be forged without volume access.
- The notification database (`webcom.db`) contains chat text and nicknames but no passwords.

## Dashboard Pages

| Page | Description |
|------|-------------|
| `/` | Live event stream (joins, messages, kicks) |
| `/servers` | Manage TeamTalk servers (add/edit/delete/connect) |
| `/users` | Whole-server roster with status/channel/client/IP, auto-refresh |
| `/notifications` | Live feed + filterable history of logins, messages, kicks, etc. |
| `/settings` | Per-server notification delivery settings (ntfy, Prowl, ...) |
| `/pmsg` | Send PMs + Message Inbox showing sent/received PMs |
| `/admin` | Run admin commands (kick, ban, broadcast, move, etc.) |
| `/logs` | Real-time application logs |

## Admin Commands

Available via `/admin` page or API. If a username matches more than one user, WebCom presents a numbered list (`1. nickname (username)`) and runs the command against your choice:

```
kick <user>                    # Kick from server
ckick <user> / kick -c <user>  # Kick from channel
kb <user>                      # Kick + ban
ban list                       # List bans
ban add user=<name>            # Add ban
broadcast <message>            # Server-wide message (requires Broadcast right)
move <user> <channel>          # Move user to channel
op <user>                      # Op a user
geolocate <user|ip>            # IP geolocation
whois <user>                   # User info
account list/add/delete        # Account management
channel list                   # List channels
file get/delete                # File management
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/events` | GET | SSE stream of live events |
| `/api/command` | POST | Run TTCom command (`{shortname, command}`) |
| `/api/users` | POST | Look up users matching a name (`{shortname, target}`) |
| `/api/users/roster` | GET | Whole-server roster (`?server=shortname`); repairs stale notification labels |
| `/api/chat` | POST | Send a channel message (`{shortname, message}`) |
| `/api/notifications` | GET | Notification history, filterable by `server`, `kind`, `direction`, `limit` |
| `/api/notifications/unread` | GET | Unread notification count (optional `server`) |
| `/api/notifications/mark-read` | POST | Mark notifications read (`{ids}` or `{server, kind, direction}`) |
| `/api/notifications/clear` | POST | Delete notifications matching `{server, kind, direction}` |
| `/api/servers/status` | GET | Per-server connection state |
| `/api/logs` | GET | Recent application logs |
| `/api/debug/bridge` | GET | Bridge connection status |

## Development

### Building Locally

```bash
docker compose build --no-cache
docker compose up -d
```

### Project Structure

```
webcom/
├── app.py                 # Flask application + API routes
├── tt_bridge.py           # PowerCom/TTCom bridge
├── config_store.py        # Configuration management
├── notification_store.py  # SQLite notification/PM history store
├── auth.py                # Argon2 authentication
├── pages/
│   └── __init__.py        # HTML templates
powercom_core/
├── features.py            # PowerCom event handling
TTComCmd.py                # TTCom command processor
ttapi.py                   # TeamTalk protocol client
conf.py                    # Configuration parser
mplib/                     # Shared libraries
```

## Troubleshooting

### Login hangs at "loggingIn"

Check `/logs` page for state transitions. Common causes:

- Wrong credentials
- Wrong host/port
- `encrypted` setting mismatch (true/false)
- Server rejects client version

### No audio notifications

Audio requires `sox` (installed in Dockerfile). WebCom publishes "speak" events to browser instead.

### Container won't start

```bash
docker compose logs webcom
```

Check for:

- Port 2032 already in use
- `./data` directory permissions
- Missing config files

## License

GPL-3.0 - Based on TeamTalk Commander by Doug Lee.

## Credits

- **TeamTalk** by BearWare.dk
- **TeamTalk Commander (TTCom)** by Doug Lee
- **PowerCom** - Enhanced TTCom fork
- **WebCom** - Headless web wrapper