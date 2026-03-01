#!/bin/sh
# Entrypoint: run as root to fix session dir (Chromium lock + permissions), then drop to appuser.
# Fixes Code: 21 "profile in use by another Chromium process" after container restarts.
set -e
SESSIONS_DIR="/app/sessions"
PROFILE_DIR="/app/sessions/session"
APP_USER="appuser"
APP_GROUP="appgroup"

echo "[entrypoint] WhatsApp container starting (cleaning Chromium profile lock)..."
if [ -d "$SESSIONS_DIR" ]; then
  # Debug: show volume contents so we can confirm lock files in logs
  echo "[entrypoint] Contents of $SESSIONS_DIR:"
  ls -la "$SESSIONS_DIR" 2>/dev/null || true
  echo "[entrypoint] Contents of $PROFILE_DIR (if present):"
  ls -la "$PROFILE_DIR" 2>/dev/null || true
  # Remove known Chromium lock files (fixed paths; no reliance on find/Busybox)
  rm -f "$PROFILE_DIR/SingletonLock" "$PROFILE_DIR/SingletonSocket" 2>/dev/null || true
  # Remove entire profile dir so no stale lock can remain (user must re-scan QR after each restart)
  rm -rf "$PROFILE_DIR" 2>/dev/null || true
  echo "[entrypoint] Cleaned Chromium profile (session dir removed)"
  # Ensure volume is writable by app user
  chown -R "$APP_USER:$APP_GROUP" "$SESSIONS_DIR" 2>/dev/null || true
else
  echo "[entrypoint] No $SESSIONS_DIR yet, skipping cleanup"
fi
echo "[entrypoint] Starting node as $APP_USER..."
exec su "$APP_USER" -s /bin/sh -c "cd /app && exec node src/server.js"
