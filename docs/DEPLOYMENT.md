# Hosting Chrozal on a DigitalOcean Droplet

## Before using an existing world

No old PostgreSQL database was supplied. Keep the original intact. Take a `pg_dump -Fc`, restore it into a disposable database, and verify startup/migrations, player login, inventory, bank contents and time. The source archive cannot recreate previously authored database content. Do not run the optional starter seed against your original database.

## First host

Provision an Ubuntu Droplet with SSH-key access. Install Docker Engine and the Compose plugin using their official instructions. Point a domain's A record at the Droplet. Start with a configuration you can benchmark; 2 vCPU / 4 GiB is an initial experiment, not a capacity promise.

Clone this branch, prepare `.env` with unique passwords, set `DOMAIN` to the real domain and `PUBLIC_ORIGIN=https://YOUR_DOMAIN`. Keep `ALLOW_REGISTRATION=false` for invitation-only testing. The origin must exactly match the browser URL, including the port for local development.

Follow the fresh setup steps in README to initialize, optionally seed, and create a named administrator. Then:

```sh
docker compose -f compose.yaml -f deploy/compose.production.yaml up -d --build
```

Caddy serves HTTPS and proxies HTTP/WebSockets to the single game process. The game port binds only to the host's loopback interface. PostgreSQL has no published host port. Use a DigitalOcean Cloud Firewall: permit 80/443 publicly, and SSH only from trusted administrative IPs. Do not publish 4000 or 5432.

Do not scale the game service to multiple containers or workers. Each process would otherwise run its own independent world and ticker. A later multi-process design needs explicit world ownership and messaging.

Review `docker compose logs --tail=100 game` and `/healthz`. The builder's logs are a bounded recent-event view; container logs rotate. Never rely on the in-memory log panel for historical incident retention.

## Backups and recovery

Run `scripts/backup.sh` from the repository directory. It writes a PostgreSQL custom-format dump with private file permissions and moves the temporary file into place only after successful completion.

Schedule this daily or more frequently on the Droplet, and separately copy completed dumps to private off-host storage such as DigitalOcean Spaces. Configure that service with scoped credentials and a retention policy. Neither off-host upload nor a cron schedule is automatically configured by this repository. Droplet snapshots complement logical database backups; they do not replace restore tests.

Example cron entry, replacing `/opt/chrozal` with the real checkout path:

```cron
15 3 * * * cd /opt/chrozal && ./scripts/backup.sh >> /opt/chrozal/backups/backup.log 2>&1
```

Restore a dump into a **new test database** using `pg_restore --no-owner --exit-on-error`. Point a separate test application at it and verify account login, room counts, equipment, item locations, relic discovery, and the latest journal entries. Record how long restoration takes. Never run destructive restore options against production as a routine check.

## Measure 100 players

On a disposable deployment with the development dependencies installed:

```sh
DATABASE_URL='postgresql://TEST_USER:TEST_PASSWORD@localhost:5432/chrozal_test' \
python scripts/load_test.py --confirm-disposable-database \
  --url wss://TEST_DOMAIN/ws --origin https://TEST_DOMAIN \
  --players 100 --rounds 30 --output load-test-result.json
```

The script creates namespaced accounts, characters and authenticated session fixtures, then removes those accounts. It bypasses the login screen only by provisioning legitimate sessions in the test database. HTTP login throughput is therefore **not** measured. Never run it on a production database.

This first workload puts all 100 players in one room, waits for HUD updates, and measures broadcast acknowledgments. It is not a full game load certification. Extend it with combat, NPC movement, inventory operations, concurrent crafting, autosave, connection churn and a sustained soak on the intended hardware.

Acceptance targets: all 100 clients present simultaneously; no unhandled exceptions or lost saves; p95 command acknowledgment under 250 ms; tick lag under 250 ms; comfortable CPU and memory headroom. Measure the latter with host/container monitoring; the included harness does not report CPU, memory or tick lag.

## Updating and rollback

Back up first. Test a release against a database clone. Arrange a maintenance window, let players log out, deploy the new image, and check health and reconnects. Builder publication and named build restores preserve connected characters; code/image deployments still require a process restart.

Keep the previous image/commit and the pre-change backup. Additive database migrations are tracked in `schema_migrations`. Reverting Python code alone does not undo database schema changes. For recovery, restore a backup into a new database and validate before switching the service.

Official references: [DigitalOcean Droplet creation](https://docs.digitalocean.com/products/droplets/how-to/create/), [Uvicorn deployment](https://uvicorn.dev/deployment/), [Uvicorn server behavior](https://uvicorn.dev/server-behavior/).
