#!/usr/bin/env bash
# Runs every minute (joan-ledger-update.timer). If GitHub has a new commit on the branch:
#   1. tests it in a separate staging checkout (the live app keeps running),
#   2. snapshots the database (last 10 kept),
#   3. switches the live checkout to the new commit and restarts,
#   4. rolls back to the previous commit if the app does not come up healthy.
# The database in /var/lib/joan-ledger is never deleted or replaced.
set -euo pipefail

APP_USER=joan
BASE=/opt/joan-ledger
APP=$BASE/app
STAGE=$BASE/staging
VENV=$BASE/venv
DATA=/var/lib/joan-ledger
DB=$DATA/ledger.db
BRANCH="${REPO_BRANCH:-main}"
FAILED=$DATA/failed-commit
KEEP_SNAPSHOTS=10

exec 9>/run/joan-ledger-update.lock
flock -n 9 || exit 0

as_app() { runuser -u "$APP_USER" -- "$@"; }
log() { echo "[deploy] $*"; }

healthy() {
  for _ in $(seq 1 30); do
    curl -fs http://127.0.0.1:8000/api/health >/dev/null && return 0
    sleep 1
  done
  return 1
}

current=$(as_app git -C "$APP" rev-parse HEAD)
remote=$(as_app git -C "$APP" ls-remote origin "refs/heads/$BRANCH" | cut -f1)
[ -n "$remote" ] || { log "could not read GitHub"; exit 0; }
[ "$remote" = "$current" ] && exit 0
[ -f "$FAILED" ] && [ "$(cat "$FAILED")" = "$remote" ] && exit 0   # already tried and failed; wait for a new commit

log "new commit ${remote:0:7} (live ${current:0:7})"
as_app git -C "$APP" fetch -q origin "$BRANCH"

# 1. Test in staging.
rm -rf "$STAGE"
as_app git -C "$APP" worktree prune
as_app git -C "$APP" worktree add -q --detach "$STAGE" "$remote"
cleanup() { as_app git -C "$APP" worktree remove --force "$STAGE" 2>/dev/null || rm -rf "$STAGE"; }
trap cleanup EXIT

if ! as_app "$VENV/bin/pip" install -q -r "$STAGE/backend/requirements.txt"; then
  log "pip install failed; staying on ${current:0:7}"
  echo "$remote" > "$FAILED"; exit 1
fi
if ! ( cd "$STAGE/backend/tests" && as_app env DATABASE_PATH=/tmp/joan-test.db "$VENV/bin/python" -m unittest discover -q -p "test_*.py" ); then
  log "tests failed; staying on ${current:0:7}"
  echo "$remote" > "$FAILED"; exit 1
fi

# 2. Snapshot the database (safe while the app is running).
if [ -f "$DB" ]; then
  snap="$DATA/snapshots/ledger-$(date -u +%Y%m%d-%H%M%S)-${current:0:7}.db"
  as_app sqlite3 "$DB" ".backup '$snap'"
  ls -1t "$DATA"/snapshots/ledger-*.db 2>/dev/null | tail -n +$((KEEP_SNAPSHOTS + 1)) | xargs -r rm -f
  log "snapshot $(basename "$snap")"
fi

# 3. Switch and restart.
as_app git -C "$APP" checkout -q --detach "$remote"
systemctl restart joan-ledger || true

# 4. Health check, roll back if needed.
if healthy; then
  rm -f "$FAILED"
  # Pick up changes to this script for the next run. Replace by rename so the running copy is untouched.
  if [ -f "$APP/deploy/update.sh" ]; then
    install -m 755 "$APP/deploy/update.sh" /usr/local/bin/joan-ledger-update.new \
      && mv -f /usr/local/bin/joan-ledger-update.new /usr/local/bin/joan-ledger-update || log "could not update deploy script"
  fi
  log "live on ${remote:0:7}"
else
  log "app unhealthy on ${remote:0:7}; rolling back to ${current:0:7}"
  echo "$remote" > "$FAILED"
  as_app git -C "$APP" checkout -q --detach "$current"
  systemctl restart joan-ledger || true
  healthy && log "rolled back" || log "ROLLBACK ALSO UNHEALTHY - check: journalctl -u joan-ledger -n 50"
  exit 1
fi
