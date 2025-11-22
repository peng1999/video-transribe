#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="$(dirname "${BASH_SOURCE[0]}")/docker-compose.yml"
SERVICE="garage"
BUCKET="${GARAGE_BUCKET:-transcribe}"
KEY_NAME="${GARAGE_KEY_NAME:-admin}"
REGION="garage"
ENDPOINT="${GARAGE_ENDPOINT:-http://localhost:3900}"

echo "Waiting for garage to be ready..."
for i in {1..20}; do
  if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage status >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [[ $i -eq 20 ]]; then
    echo "Garage not ready after 20s" >&2
    exit 1
  fi
done

echo "Ensuring key $KEY_NAME exists..."
KEY_ID="$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" sh -c \
  "garage key list | awk '/^$KEY_NAME /{print \$2}'")"
if [[ -z "$KEY_ID" ]]; then
  KEY_ID="$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage key new --name "$KEY_NAME" \
    | awk '/Key ID/{print \$3}')"
  SECRET="$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage key export --full "$KEY_ID" \
    | awk '/Secret/{print \$3}')"
  echo "Created key:"
  echo "  AWS_ACCESS_KEY_ID=$KEY_ID"
  echo "  AWS_SECRET_ACCESS_KEY=$SECRET"
else
  SECRET="$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage key export --full "$KEY_ID" \
    | awk '/Secret/{print \$3}')"
  echo "Key already exists, reusing:"
  echo "  AWS_ACCESS_KEY_ID=$KEY_ID"
  echo "  AWS_SECRET_ACCESS_KEY=$SECRET"
fi

echo "Ensuring bucket $BUCKET exists..."
if ! docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage bucket info "$BUCKET" >/dev/null 2>&1; then
  docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage bucket create "$BUCKET"
fi

echo "Granting key permissions to bucket..."
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" garage bucket allow "$BUCKET" --read --write --owner --key "$KEY_ID"

cat <<EOT
Done. Use these S3 settings for the backend:
  AWS_ACCESS_KEY_ID=$KEY_ID
  AWS_SECRET_ACCESS_KEY=$SECRET
  S3_ENDPOINT=$ENDPOINT
  AWS_REGION=$REGION
  S3_BUCKET=$BUCKET
EOT
