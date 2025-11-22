#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="$(dirname "${BASH_SOURCE[0]}")/docker-compose.yml"
SERVICE="garage"
BUCKET="${GARAGE_BUCKET:-transcribe}"
KEY_NAME="${GARAGE_KEY_NAME:-admin}"
REGION="garage"
ENDPOINT="${GARAGE_ENDPOINT:-http://localhost:3900}"

log() { echo "$@"; }

compose_exec() { docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" "$@"; }

strip_ansi() { sed -r 's/\x1B\[[0-9;]*[mK]//g'; }

wait_for_garage() {
  log "Waiting for garage to be ready..."
  for i in {1..20}; do
    if compose_exec /garage status >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  log "Garage not ready after 20s" >&2
  exit 1
}

extract_node_id() {
  local status_clean="$1"
  echo "$status_clean" | awk 'header && NF {print $1; exit} /^ID[[:space:]]+Hostname/ {header=1}'
}

ensure_layout() {
  local status_raw status_clean node_id layout_show apply_version
  status_raw="$(compose_exec /garage status)"
  status_clean="$(echo "$status_raw" | strip_ansi)"
  node_id="$(extract_node_id "$status_clean")"
  if [[ -z "$node_id" ]]; then
    log "Could not determine Garage node ID from status output" >&2
    echo "$status_raw"
    exit 1
  fi
  if echo "$status_clean" | grep -Eq "NO ROLE ASSIGNED|pending"; then
    log "Assigning single-node layout (node $node_id, zone 1, capacity 1024)..."
    compose_exec /garage layout assign --capacity 1024 --zone 1 "$node_id"
  fi
  if echo "$status_clean" | grep -Eq "NO ROLE ASSIGNED|pending"; then
    layout_show="$(compose_exec /garage layout show)"
    apply_version="$(echo "$layout_show" | awk '/layout apply --version/ {print $NF; exit}')"
    if [[ -z "$apply_version" ]]; then
      log "Could not determine layout version to apply" >&2
      echo "$layout_show"
      exit 1
    fi
    log "Applying staged layout (version $apply_version)..."
    compose_exec /garage layout apply --version "$apply_version" >/dev/null
  fi
}

ensure_key() {
  local key_id key_secret create_output
  key_id="$(compose_exec /garage key list | awk -v name="$KEY_NAME" 'NF>=3 && $3==name {print $1; exit}')"
  if [[ -z "$key_id" ]]; then
    create_output="$(compose_exec /garage key create "$KEY_NAME")"
    key_id="$(echo "$create_output" | awk -F': *' '/Key ID/{print $2}')"
    key_secret="$(echo "$create_output" | awk -F': *' '/Secret key/{print $2}')"
    log "Created key:"
    log "  AWS_ACCESS_KEY_ID=$key_id"
    log "  AWS_SECRET_ACCESS_KEY=$key_secret"
  else
    log "Key already exists, reusing:"
    log "  AWS_ACCESS_KEY_ID=$key_id"
    log "  AWS_SECRET_ACCESS_KEY=<unavailable; reuse previously saved secret>"
    key_secret="<unavailable>"
  fi
  KEY_ID="$key_id"
  SECRET="$key_secret"
}

ensure_bucket() {
  if ! compose_exec /garage bucket info "$BUCKET" >/dev/null 2>&1; then
    compose_exec /garage bucket create "$BUCKET" >/dev/null
  fi
}

grant_permissions() {
  compose_exec /garage bucket allow "$BUCKET" --read --write --owner --key "$KEY_ID" >/dev/null
}

print_config() {
  cat <<EOT
Done. Use these S3 settings for the backend:
  AWS_ACCESS_KEY_ID=$KEY_ID
  AWS_SECRET_ACCESS_KEY=$SECRET
  S3_ENDPOINT=$ENDPOINT
  AWS_REGION=$REGION
  S3_BUCKET=$BUCKET
EOT
}

main() {
  wait_for_garage
  ensure_layout
  ensure_key
  ensure_bucket
  grant_permissions
  print_config
}

main
