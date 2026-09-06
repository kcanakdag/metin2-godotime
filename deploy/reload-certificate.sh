#!/usr/bin/env bash
# Managed for metin2-godotime. Certbot deploy hook: reload only this game's nginx.
set -euo pipefail
cd /opt/metin2-godotime
test -f .certificate || exit 0
if test -n "${RENEWED_LINEAGE:-}" && test "${RENEWED_LINEAGE##*/}" != "$(cat .certificate)"; then
    exit 0
fi
if test -n "$(docker compose ps -q web)"; then
    docker compose exec -T web nginx -t
    docker compose exec -T web nginx -s reload
fi
