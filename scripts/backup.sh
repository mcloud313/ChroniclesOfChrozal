#!/bin/sh
set -eu
umask 077
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="backups/chrozal-${stamp}.dump"
docker compose exec -T db pg_dump -U chrozal -d chrozaldb -Fc > "${file}.partial"
test -s "${file}.partial"
mv "${file}.partial" "$file"
printf 'Backup written: %s\n' "$file"
# Copy this completed dump off-host. Local copies do not survive loss of the Droplet.
