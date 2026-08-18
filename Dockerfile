# WebCom - PowerCom re-delivered as accessible web pages.
# Security model (per owner's requirements):
#   - Runs as a NON-ROOT user inside the container (the container IS the jail,
#     in the same spirit as firejail for the media bot).
#   - TeamTalk server credentials are stored PLAINTEXT by TeamTalk's own design
#     (bearware will not fix this). They live ONLY in the mounted /data volume
#     (config.local.json / generated ttcom.conf), never in the image or repo.
#   - The web dashboard login is argon2-hashed (separate from TT creds).
#   - The only writable path is /data (the volume). The app filesystem is read-only
#     at runtime except for that mount.
FROM python:3.14-slim

# Run as non-root from the start.
RUN groupadd -r webcom && useradd -r -g webcom -m -d /home/webcom webcom

# Trimmed dependency set: drop wxpython / sound_lib / pywin32 (desktop/audio deps
# irrelevant to a headless Linux container). Keep what TTComCmd + notifiers need.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what's needed to install deps first (better layer caching).
COPY requirements-webcom.txt /app/requirements-webcom.txt
RUN pip install --no-cache-dir -r requirements-webcom.txt

# Copy the full PowerCom fork + webcom wrapper.
COPY . /app

# The data volume holds all secrets + generated config. Owned by webcom.
RUN mkdir -p /data && chown -R webcom:webcom /data /app
USER webcom

# Port 2032 (WebCom dashboard). Bind handled by docker-compose (0.0.0.0 default).
EXPOSE 2032

# Run with the PowerCom dir as cwd so conf.py / TTComCmd resolve correctly.
WORKDIR /app
CMD ["python", "-m", "webcom.app"]
