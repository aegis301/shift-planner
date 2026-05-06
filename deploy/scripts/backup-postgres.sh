#!/usr/bin/env sh
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${1:-$ROOT/backups/postgres-$(date +%Y%m%d-%H%M%S).sql}"
mkdir -p "$(dirname "$OUT")"
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' >"$OUT"
echo "Wrote $OUT"
