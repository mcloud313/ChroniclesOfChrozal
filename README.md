# Chronicles of Chrozal

A persistent, roleplay-focused Python fantasy MUD. This revival branch restores browser play, a character HUD, an authenticated builder, and an optional 100-room level 1–20 QA slice for twelve classes. PostgreSQL remains the authoritative store.

**0.2.0-alpha:** Existing installations should start with [the database-preserving upgrade guide](docs/UPGRADE-0.2.md). See [implementation, limitations and next milestones](docs/REVIVAL.md). The target is 100 concurrent players; hosting capacity must be measured on the intended Droplet. No existing database dump is included in this repository.

Review [roadmap status](docs/ROADMAP_STATUS.md) and the [whole-project QA guide](docs/QA.md). Start with the [Bazzite development guide](docs/BAZZITE.md) and [playtest guide](docs/PLAYTEST.md). Cloud deployment follows local testing.

## Run a fresh world with Docker Compose

1. Copy `.env.example` to `.env`. Replace both password placeholders with the same unique password. For a local trial leave `PUBLIC_ORIGIN=http://localhost:8000` and registration disabled.
2. Build and start PostgreSQL:

   ```sh
   docker compose build
   docker compose up -d db
   docker compose run --rm game python scripts/manage.py init
   docker compose run --rm game python scripts/manage.py seed
   docker compose run --rm game python scripts/manage.py expand-slice
   docker compose run --rm game python scripts/manage.py account andrew you@example.com --admin
   docker compose up -d game
   ```

3. Open `http://localhost:8000`, sign in and follow character selection/creation. Open `/admin` for the builder. Creating the account prompts for a password rather than exposing it in shell history. Create friends' accounts with the same command without `--admin`.

The optional seed refuses to replace an existing authored world. Start at Wayfinder's Plaza, talk to Mira during the day, gather silverleaf south of the plaza, and craft coast salve at the Tideforge east of the plaza. The old observatory lies two rooms north. Type `quest` at a notice board to reserve a daily contract, `technique` for your class kit, and `treat` to use a crafted salve.

## Existing database

Back it up and restore a disposable copy first. Set `DATABASE_URL` to that copy and run `python scripts/manage.py init` from an installed environment. Test login, equipment, saved locations and game time before using the original. The revival migrations are additive; the original bootstrap is not a comprehensive migration system for every historical schema.

The old source contained credentials and auto-created `admin`/`tester` accounts. Rotate any reused database password. On your database clone inspect those accounts, then explicitly run `python scripts/manage.py disable-legacy-accounts` to randomize their passwords and remove admin privileges. Create a new named administrator. Code cleanup does not erase old Git history.

## Python development

Python 3.12 is the tested development version. Use a PostgreSQL 16 server and export configuration values into your shell (the Python entry point does not auto-load `.env`).

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL='postgresql://USER:PASSWORD@localhost:5432/chrozaldb'
export PUBLIC_ORIGIN='http://localhost:8000'
python scripts/manage.py init
python server.py
```

Always start **one** server process. Do not use multiple workers: the live world lives in memory. No Telnet service is started.

## Tests

```sh
python -m pytest -q
# Integration tests create data: use only an empty disposable test database.
TEST_DATABASE_URL='postgresql://USER:PASSWORD@localhost:5432/chrozal_test' python -m pytest -q
```

See [verification](docs/VERIFICATION.md) for what actually ran, and [deployment](docs/DEPLOYMENT.md) for HTTPS hosting, backups and load testing.
