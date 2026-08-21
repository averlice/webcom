# WebCom

WebCom is a headless TeamTalk text client delivered as a web dashboard. Based on PowerCom (a fork of TeamTalk Commander).

## Features

- **Web Dashboard** - Access TeamTalk from any browser
- **Multi-server support** - Connect to multiple TeamTalk servers
- **Real-time events** - Live event stream via Server-Sent Events (SSE)
- **Admin commands** - Kick, ban, broadcast, move users, etc.
- **TTCom Private Messages** - Invisible to desktop clients
- **Notifications** - ntfy, Prowl, Pushover, MG Notify, system notifications
- **Logs page** - Real-time application logs in the browser
- **Server management** - Add/edit/remove servers via UI

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
4. Save and login

## Configuration

All persistent data lives in the `./data` volume (gitignored):

```
data/
├── config.local.json    # WebCom config (web admin hash + TT servers)
└── ttcom.conf           # Generated PowerCom config (auto-generated)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBCOM_DATA_DIR` | `/data` | Data volume path |
| `WEBCOM_PORT` | `2032` | HTTP port |
| `WEBCOM_BIND` | `0.0.0.0` | Bind address |

### Security Notes

- **TeamTalk passwords** are stored in plaintext in `config.local.json` - this is a TeamTalk protocol requirement, not our choice
- **Web dashboard passwords** are argon2-hashed (stored in `config.local.json` as `admin_hash`)
- The `./data` directory should be backed up and never committed to git
- Session cookies are signed with a random secret stored in config

## Dashboard Pages

| Page | Description |
|------|-------------|
| `/` | Live event stream (joins, messages, kicks) |
| `/servers` | Manage TeamTalk servers (add/edit/delete) |
| `/notifications` | Configure per-server notifications |
| `/pmsg` | Send TTCom private messages (invisible to desktop clients) |
| `/admin` | Run admin commands (kick, ban, broadcast, move, etc.) |
| `/logs` | Real-time application logs |

## Admin Commands

Available via `/admin` page or API:

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
├── app.py              # Flask application
├── tt_bridge.py        # PowerCom/TTCom bridge
├── config_store.py     # Configuration management
├── auth.py             # Argon2 authentication
├── pages/
│   └── __init__.py     # HTML templates
powercom_core/
├── features.py         # PowerCom event handling
TTComCmd.py             # TTCom command processor
ttapi.py                # TeamTalk protocol client
conf.py                 # Configuration parser
mplib/                  # Shared libraries
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