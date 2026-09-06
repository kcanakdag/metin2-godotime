#!/usr/bin/env bash
# Apply one pre-staged release. Never delete, restore, or migrate a database destructively.
set -Eeuo pipefail
release=$1
database=$2
public_name=$3
game_port=$4
certificate=$5
game_root=/opt/metin2-godotime
candidate=$game_root/incoming/$release
backup=$game_root/backups/$release
hook=/etc/letsencrypt/renewal-hooks/deploy/metin2-godotime
phase=preflight
old_db=
stopped_db=
old_image=
old_image_tag=
runtime_changed=0
recover_database=1
web_changed=0
old_web=

cd "$game_root"
exec 9>deployment.lock
flock -n 9 || { echo 'Another game deployment is running' >&2; exit 1; }

record_phase() {
    printf '{"release":"%s","phase":"%s"}\n' "$release" "$phase" >"$candidate/status.json"
    cp "$candidate/status.json" deployment-status.json
}

finish() {
    result=$?
    if test "$result" -ne 0; then
        set +e
        echo "Game deployment failed during $phase; candidate: $candidate; backup: $backup" >&2
        if test "$runtime_changed" = 1 && test "$recover_database" = 1 && test -f "$backup/runtime/compose.yaml"; then
            # Only before publication: restore the old executable/configuration, never its data.
            cp -a "$backup/runtime/." "$game_root/"
            if test -n "$old_image" && test -n "$old_image_tag"; then
                docker image tag "$old_image" "$old_image_tag"
            fi
            docker compose up -d --no-deps db
        elif test -n "$stopped_db" && docker inspect "$stopped_db" >/dev/null 2>&1; then
            docker start "$stopped_db" >/dev/null
        fi
        if test "$web_changed" = 1 && test -n "$old_web"; then
            ln -sfn "$old_web" web/current.rollback
            mv -Tf web/current.rollback web/current
            cp "$backup/runtime/nginx.conf" nginx.conf
            cp "$backup/runtime/.env" .env
            docker compose up -d --no-deps --force-recreate web
        fi
        phase="failed:$phase"
        record_phase
    fi
}
trap finish EXIT
record_phase

for executable in docker curl ss ufw openssl; do command -v "$executable" >/dev/null; done
docker compose version >/dev/null
test -f "/etc/letsencrypt/live/$certificate/fullchain.pem"
test -f "/etc/letsencrypt/live/$certificate/privkey.pem"
openssl x509 -in "/etc/letsencrypt/live/$certificate/fullchain.pem" -noout -checkhost "$public_name" >/dev/null
openssl x509 -in "/etc/letsencrypt/live/$certificate/fullchain.pem" -noout -checkend 86400 >/dev/null
if test -e "$hook" && ! grep -q '^# Managed for metin2-godotime\.' "$hook"; then
    echo 'The game certificate hook path belongs to another script' >&2
    exit 1
fi
for port in "$game_port" 13210; do
    if ss -H -lnt "sport = :$port" | grep -q .; then
        docker ps --filter label=com.docker.compose.project=metin2-godotime --format '{{.Ports}}' |
            grep -q ":$port->" || { echo "Port $port belongs to another service" >&2; exit 1; }
    fi
done
mkdir -p web/releases backups
chmod 700 backups
mkdir -m 700 "$backup" "$backup/runtime"
for name in Dockerfile compose.yaml .dockerignore nginx.conf .env .certificate mt2_server.wasm; do
    if test -f "$name"; then cp -a "$name" "$backup/runtime/$name"; fi
done
if test -L web/current; then old_web=$(readlink web/current); fi
printf '%s\n' "$old_web" >"$backup/previous-web.txt"
if test -f compose.yaml; then old_db=$(docker compose ps -aq db); fi
if test -n "$old_db"; then
    old_image=$(docker inspect --format '{{.Image}}' "$old_db")
    old_image_tag=$(docker inspect --format '{{.Config.Image}}' "$old_db")
    printf '%s\n' "$old_image" >"$backup/previous-image.txt"
fi

phase=validating
record_phase
docker compose -p metin2-godotime --project-directory "$candidate" -f "$candidate/compose.yaml" config --quiet
# Resolve the upstream for a syntax check without starting a second server or binding any ports.
web_image=$(docker compose -p metin2-godotime --project-directory "$candidate" -f "$candidate/compose.yaml" config --images | sed -n '/^nginx:/p')
docker run --rm --network none --add-host db:127.0.0.1 \
    -v "$candidate/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v /etc/letsencrypt:/etc/letsencrypt:ro "$web_image" nginx -t
docker compose -p metin2-godotime --project-directory "$candidate" -f "$candidate/compose.yaml" build db

phase=backing-up
record_phase
if test -n "$old_db"; then
    stopped_db=$old_db
    docker stop "$stopped_db" >/dev/null
    docker cp "$stopped_db:/data" "$backup/world"
fi
runtime_changed=1
for name in Dockerfile compose.yaml .dockerignore nginx.conf .env .certificate mt2_server.wasm; do
    install -m 644 "$candidate/$name" "$name"
done
chmod 600 .env .certificate
phase=starting-database
record_phase
docker compose run --rm --no-deps --user 0 --entrypoint sh db -c 'chown 1000:1000 /data && chmod 700 /data'
docker compose up -d --no-deps db
timeout 30 sh -c 'until curl --silent --max-time 2 --output /dev/null http://127.0.0.1:13210/; do sleep 1; done'
if test -f "$backup/world/config/spacetime/id_ecdsa.pub"; then
    previous_key=$(sha256sum "$backup/world/config/spacetime/id_ecdsa.pub" | cut -d ' ' -f 1)
    current_key=$(docker compose exec -T db sha256sum /data/config/spacetime/id_ecdsa.pub | cut -d ' ' -f 1)
    test "$previous_key" = "$current_key" || { echo 'The database issuer key changed unexpectedly' >&2; exit 1; }
fi
stopped_db=
recover_database=0
phase=publishing
record_phase
docker compose exec -T db spacetime --config-path /data/publisher-v2.toml publish \
    --server http://127.0.0.1:3000 --bin-path /game/mt2_server.wasm "$database" \
    --no-config --delete-data=never --yes=remote,skip-login,migrate
docker compose exec -T db chmod 600 /data/publisher-v2.toml

phase=activating-web
record_phase
mv "$candidate/web" "web/releases/$release"
ln -s "releases/$release" "web/current.$release"
web_changed=1
mv -Tf "web/current.$release" web/current
docker compose up -d --no-deps --force-recreate web
docker compose exec -T web nginx -t
timeout 30 sh -c 'until curl --silent --fail --max-time 2 --resolve "$1:$2:127.0.0.1" "https://$1:$2/health" >/dev/null; do sleep 1; done' sh "$public_name" "$game_port"
expected_manifest=$(sha256sum "web/releases/$release/build-manifest.json" | cut -d ' ' -f 1)
served_manifest=$(curl --silent --fail --max-time 10 --resolve "$public_name:$game_port:127.0.0.1" "https://$public_name:$game_port/build-manifest.json" | sha256sum | cut -d ' ' -f 1)
test "$expected_manifest" = "$served_manifest"
mkdir -p "${hook%/*}"
install -m 755 "$candidate/reload-certificate.sh" "$hook"
ufw allow "$game_port/tcp" comment 'metin2-godotime browser game'
web_changed=0
phase=ready
record_phase
echo "Game release $release is serving its verified manifest; database files and issuer keys remain in the world volume."
