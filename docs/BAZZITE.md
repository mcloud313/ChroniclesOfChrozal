# Bazzite development first

This development checkout is prepared for testing on Andrew's Bazzite machine before any cloud deployment. These commands have not been executed on that machine.

## Container-based local trial

Bazzite documents containers and Distrobox as development options. Use the host terminal for Podman; do not install PostgreSQL into the immutable base system.

```sh
mkdir -p ~/Projects
cd ~/Projects
# Extract the delivered Chrozal-QA-Build.zip here first.
cd Chrozal-QA/source
podman --version
podman compose version
python3 scripts/configure_local.py
```

The configuration script generates a unique database password and creates `.env` with private permissions. It retains an existing file. Leave `PUBLIC_ORIGIN=http://localhost:8000` and `ALLOW_REGISTRATION=false` for this trial.

`podman compose` needs an installed Compose provider; it is a wrapper, not the provider itself. If the version check fails, set up Compose using the official Podman Desktop Compose instructions linked below, then repeat the check. Avoid layering unrelated packages onto Bazzite merely to run this project.

```sh
podman compose build
podman compose up -d db
podman compose run --rm game python scripts/manage.py init
podman compose run --rm game python scripts/manage.py seed
podman compose run --rm game python scripts/manage.py qa-accounts
podman compose up -d game
```

Open **http://localhost:8000** in Firefox. Use that exact hostname; origin checks deliberately distinguish it from `127.0.0.1`. The application binds only to loopback for this trial. `/admin` uses the same account and session.

The database uses a named persistent volume. Ordinary `podman compose down`, rebuilds and restarts retain it. **Do not use `down -v`** unless you explicitly intend to destroy this disposable development world.

## Develop and verify

Edit the source in your usual editor, then:

```sh
podman compose up -d --build game
podman compose logs --tail=100 game
```

For a Python debugger, use a Distrobox development container or the included Dev Container configuration. Database authentication and the exact browser origin must still match the running environment. Rootless Podman/SELinux may require a `:Z` bind mount when introducing source mounts; the default trial uses a built image and named volume, so it does not need a source bind mount.

See [QA.md](QA.md) for account details and the complete project acceptance checklist.

## Suggested hands-on session

1. Create one character from each class. Roll scores and assign them to your preferred attributes. Confirm you can reconnect with the same character, location and equipment.
2. At the plaza: `quest`, `quest accept 1`, `technique`. Talk to Mira at the plaza by day or the tavern by night. Gather silverleaf south of the plaza, and explore east from Serpent Road.
3. Accept contracts from a notice board, return there, then `quest complete`. Absorb experience at a node and `advance`. Eat, drink and rest between trips.
4. Try the class basic technique, the level-3 signature, and the level-7 finale. Watch enemy wind-ups; `brace` can be used during recovery. Try a retreat rather than repeating the same attack.
5. Craft a salve and charm. Test inventory, dropping/picking up, banking, and reconnecting. Log anything confusing or tedious.
6. With a character still connected, save a named build state, edit a room description, and publish. Confirm the client stays connected and its HP/location/inventory remain intact. Restore the saved definitions and confirm the description returns.
7. Wound an NPC, drop an item, complete a contract, then stop and restart the game service. Check that runtime state reloads. Wait for the periodic checkpoint before a simulated hard interruption; graceful shutdown saves immediately.
8. Run the integration suite against a separate disposable database before importing any older data.

The authored build-state restore is a merge: it restores rows represented in the saved state and preserves later-added entities. It never rolls player progress backward. Exact destructive world rollback is deliberately separate from this workflow.

## Back up the local trial

```sh
mkdir -p backups
podman compose exec -T db pg_dump -U chrozal -d chrozaldb -Fc > backups/chrozal-development.dump
```

Copy valuable dumps somewhere separate before making larger changes. Save a dump of any original 2025 world before attempting its import.

References: [Bazzite Distrobox](https://docs.bazzite.gg/Installing_and_Managing_Software/Distrobox/), [Bazzite containers](https://docs.bazzite.gg/Installing_and_Managing_Software/Containers/), [Podman Compose](https://docs.podman.io/en/latest/markdown/podman-compose.1.html), [Compose setup in Podman Desktop](https://podman-desktop.io/tutorial/getting-started-with-compose).
