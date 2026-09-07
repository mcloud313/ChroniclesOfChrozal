# Upgrade your existing Bazzite test world to 0.2.0-alpha

Use your **existing project directory and the same Compose project name**. Changing the directory/project name can make Compose create a different database volume and make your world appear empty. Do not run `seed`, delete volumes, or use `down -v` for an upgrade.

## 1. Back up before replacing code

Open a terminal in the directory where your current `compose.yaml` and `.env` live. These commands use the same `podman compose` provider as your existing installation.

```sh
mkdir -p ../chrozal-backups
podman compose stop game
podman compose exec -T db pg_dump -U chrozal -d chrozaldb -Fc > ../chrozal-backups/pre-0.2.dump
cp .env ../chrozal-backups/pre-0.2.env
chmod 600 ../chrozal-backups/pre-0.2.env
podman compose exec -T db pg_restore -l < ../chrozal-backups/pre-0.2.dump
```

The last command must list archive contents. If your database username/name differs, use your configured values. Keep your existing code checkout as the code rollback point. Record `git rev-parse HEAD` and `podman compose ps`. Your backup contains account and character data: keep it private.

## 2. Apply the bundled Git history (recommended)

Extract the new ZIP somewhere separate, such as `~/Downloads/Chrozal-QA-0.2`. In your existing Git checkout:

```sh
git status --short
```

If you have local changes, commit them or copy them aside first. The archive includes `chrozal-0.2.bundle`, with history based on your pushed `5303dbf` build.

```sh
git fetch ~/Downloads/Chrozal-QA-0.2/chrozal-0.2.bundle qa/desktop-0.2
git merge --ff-only FETCH_HEAD
```

Adjust the extracted path if needed. If the fast-forward fails, keep your local changes and inspect the divergence; do not reset hard. The bundle is the exact delivered version. After QA, you can push this commit through your existing authenticated GitHub setup.

If the current installation has no Git checkout, copy the ZIP's `source/` files over that **same existing directory**. Retain `.env`, database volumes and log volumes. The ZIP contains no local credentials or database files. Do not extract into a new directory and start Compose there.

## 3. Rebuild and migrate without resetting

```sh
podman compose build game
podman compose run --rm game python scripts/manage.py init
podman compose run --rm game python scripts/manage.py expand-slice
podman compose up -d game
podman compose logs --tail=100 game
```

`init` applies additive migrations 012–018. `expand-slice` adds the new world content exactly once; it retains the original 15 rooms and your character/build states. You can omit the expansion if you only want engine fixes. This pack expects the original Port Valis starter landmarks and will stop if they are absent.

Open `http://localhost:8000`, hard-refresh the browser, and sign in with your existing accounts. First test `n`, wait for roundtime, `south`, then the north button. Do not recreate your existing administrator/test accounts.

For the new class, create a Tempest normally on the test account, or run `podman compose run --rm game python scripts/manage.py qa-add-missing` to add missing class fixtures without changing existing characters. Existing characters retain their rolled stats, coinage and inventory. New characters use the new race list and dice rolls. The QA account provisioner is for fresh installations; it deliberately refuses existing accounts.

## 4. First QA circuit

1. From the plaza, go west to the tavern during shop hours (07:00–21:00 game time). `list`, `buy travel ration`, `eat travel ration`, `buy spring water`, `drink spring water`, `rest`. Wait out movement roundtime before buying. Eating when full must not disconnect you. Compare regeneration here with a room without NODE.
2. Buy a traveler pack, `wear traveler pack`, `open traveler pack`. Move held items into it. A closed container must block access. `sheathe` stores a weapon in an open carried container; `unsheathe <weapon>` retrieves it. Test a filled container through deposit and withdrawal without reconnecting. Inspect GUIDs and container links in the administrator's item-instance catalog.
3. For ranged QA: buy and wear a coast quiver; open it; buy an arrow bundle and put it in the quiver; buy and wield a coast bow. `shoot <enemy>` consumes one arrow and imposes bow roundtime even on a miss. A shield, occupied loading hand or absent ammo must stop the shot.
4. `quest` at a board, `quest accept <id>`, perform its objectives, return and `quest complete`. A second acceptance is rejected while active. A finished notice disappears for everyone; the next game day produces a fresh set. Party contracts require exactly the listed party size and everyone present for progress/turn-in.
5. Try `recover`, `chapters`, `relics` and `attune`: none should be offered as player actions. Legendary relics are intended for level 50+, so the level-20 expansion awards none.
6. Inspect the new area selector, edit a room, inspect its exit buttons, connect rooms using the exit form, publish, and walk through the connection. Test the Door/River/Rockwall presets. Save a build state, alter a description, restore it, and confirm characters and items remain.
7. Use the trapped lockbox in the plaza to test search, disarm, lockpick and open. Failed traversal can cause HP loss and prone stance; `stand` before continuing.
8. Close the tab and return within five minutes. Your character should resume, including its location and combat state. During that interval the character remains vulnerable. A healthy background tab sends heartbeats; mobile browser suspension can interrupt them. Safe Disconnect works in a safe room out of combat. Outside safety, `quit` is rejected.
9. Toggle auto-scroll, view the character sheet, check time played, compare combat colors and try the mobile layout. The online list marks link-lost characters.
10. Test with an ordinary account: `/admin`, `/static/admin.html`, `/static/admin.js`, all `/api/admin/*` endpoints and build publication must be denied. Hiding a menu alone is not the access control.
11. Inspect live players, GUID inventories, XP pools, conditions and metrics. Download the warning/error archive when reporting a bug. It is preserved in the existing log volume.

## 5. Accounts and recovery

Existing accounts remain verified for this upgrade. Leave `ALLOW_REGISTRATION=false` during local testing. To test password reset locally without email:

```sh
podman compose run --rm game python scripts/manage.py recovery-code YOUR_TEST_USERNAME
```

Paste the printed code into the Account recovery panel with a new password of at least 12 characters. Codes expire after 30 minutes, work once, and password reset revokes sessions. Never include a code/password in a bug report.

For public email delivery, set SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD and MAIL_FROM in `.env`, using your mail provider's STARTTLS relay. Recreate the game container after configuration changes. New public registrations must verify email before sign-in. Verification requests and reset responses do not reveal whether an address exists. No email provider has been configured or exercised by this delivery.

Email verification and server command limits deter abuse but do not prove human play or prevent browser automation. One active play connection per account is enforced; distinct-account abuse requires moderation and further evidence, not just IP blocking.

## 6. Automated and manual acceptance

Run tests only against a disposable PostgreSQL database, using `docs/QA.md` for the existing native PostgreSQL procedure. The suite creates fixture accounts, content and test items. Never point TEST_DATABASE_URL at your play database.

Use the previous full QA checklist for retained soul-tether, XP, gathering, crafting, lighting, weather, banking, housing and persistence checks, with these replacements: notice boards replace chapters; food/drink/rest replace recover; mail is letters only; trading needs level 10. The verification report identifies what was actually executed here.

For a useful bug report include build version, character/class/level, room ID, exact commands and responses, expected result, server warning/error excerpt and whether it reproduces after reconnect. Do not include passwords, session cookies, recovery codes or your `.env`.

## Rollback

Keep the pre-upgrade code and dump. Do not run old code against the upgraded database as a casual rollback. Stop the game; restore the dump into a **separate fresh PostgreSQL database/volume** and use the previous code/config pointed at that restored database. Validate the restored characters and rooms before switching. Preserve the upgraded database until you have confirmed the restore. This avoids deleting the only copy of your world.
