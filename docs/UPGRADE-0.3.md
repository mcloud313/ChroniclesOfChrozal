# Upgrade to 0.3.0-alpha on Bazzite

Use the same project directory, Compose project name, configuration and database volume as your running world. **Do not run `seed` or `down -v`.** This build adds migration 019 and starter equipment without resetting characters, rooms, builds or accounts.

## Back up and replace the code

In your existing project directory:

```sh
mkdir -p ../chrozal-backups
podman compose stop game
podman compose exec -T db pg_dump -U chrozal -d chrozaldb -Fc > ../chrozal-backups/pre-0.3.dump
podman compose exec -T db pg_restore -l < ../chrozal-backups/pre-0.3.dump
cp .env ../chrozal-backups/pre-0.3.env
chmod 600 ../chrozal-backups/pre-0.3.env
git status --short
git rev-parse HEAD
```

Use your configured database username/name if different. The archive listing must succeed. Save the old Git commit and preserve any uncommitted work before proceeding.

Extract `Chrozal-QA-0.3.zip` under Downloads, separate from your installation. The preferred update imports the included version history:

```sh
git fetch ~/Downloads/Chrozal-QA-0.3/chrozal-0.3.bundle qa/desktop-0.3
git merge --ff-only FETCH_HEAD
podman compose build game
podman compose run --rm game python scripts/manage.py init
podman compose up -d game
podman compose logs --tail=100 game
```

Adjust the extracted path if needed. If Git reports divergence, preserve your work and resolve it; do not reset hard. The bundle includes the 0.2 commits and this iteration, based on `5303dbf`. If you do not have a Git checkout, copy **the contents of `source/`** over the same existing project directory, retaining configuration, logs and database volumes, then run the build/init/up commands above.

Hard-refresh the browser after updating. Existing login credentials still work. There is no need to rerun the world expansion if you already have the 100-room slice.

## First-login administrator

`python scripts/manage.py init` creates username **admin** only when no administrator exists and that username/email is available. It generates a unique temporary password and prints it once to your terminal. Save that password securely; there is no shared password embedded in the source or ZIP.

The first login displays a password-change form. Play, administrator APIs and the builder remain blocked until you choose a different password of at least 12 characters. Then sign in again. Running init again never resets an existing administrator. If a legacy non-admin account already occupies `admin`, create a differently named administrator with `python scripts/manage.py account <username> <email> --admin`. This avoids taking over existing accounts.

Public signup still requires `ALLOW_REGISTRATION` and configured SMTP verification. New accounts cannot log in until verified. Existing accounts remain verified. The password-reset/verification controls are under Account recovery; the previous upgrade guide documents SMTP settings and the local `recovery-code` command. No email delivery provider is configured by this download.

## Reproduce and verify the hand fix

1. Sign in with the affected character. Migration 019 supplies a traveler backpack, shirt, trousers and boots in vacant equipment slots. Existing gear is preserved. Excess loose items from the old bug are stowed into an open worn container where capacity permits; GUIDs remain unchanged. Any unresolved overflow is reported with its GUID.
2. Check `inventory`. Held instances list their GUID and hand; equipped gear lists its slot and name. `open traveler backpack` if necessary.
3. Wield your dagger, go to Saltwind Strand and `gather silverleaf`. With the dagger in one hand, one leaf fills the other. A second gather must refuse without consuming the resource.
4. `put silverleaf in traveler backpack` frees one hand. Gathering can then succeed once more. Use `sheathe` to stow a wielded weapon into a real open container; `unsheathe wayfarer dagger` retrieves it. Commands using an occupied two-handed weapon must refuse hand work.
5. Put a leaf away, close the backpack, and try `get silverleaf from traveler backpack`: it must refuse. Open it and retry. Watch capacity and hand occupancy.
6. `destroy <GUID>` must only prompt. `destroy confirm` within 30 seconds deletes that exact held instance. Expired confirmations, moved instances, relics and nonempty containers cannot be destroyed. Remove equipment before destroying it. Duplicate names require a GUID.
7. Below level 10, dropping/trading remains restricted. At level 10, drop a held item, look for it on the ground, then get it again. Coins remain in your purse.
8. Safely disconnect and reconnect, then restart the server and check every item's location/GUID again. Test nested containers as well as a worn backpack.

## Combat, rescue and progression

- Fight a scavenger while a second character watches. Both should see attacks, misses and **CRITICAL HIT** messages; participants and room observers receive hit math. Critical output is bold crimson with a red accent. There are no wind-up/brace prompts or brace button/command.
- Physical attacks roll against dodge, with existing parry/block checks, then apply physical damage soak, armor and percentage resistance. Magical attacks roll against dodge, then apply spell damage soak, barrier and percentage resistance. Armor no longer substitutes for a magical barrier; barrier no longer substitutes for armor. Even formerly automatic-hit attack spells now make dodge rolls. Protective class signatures create temporary magical barriers.
- Test bows with an open quiver and compatible ammunition. Bow damage now uses the bow's stats. Both hands are occupied when wielding a bow; ammunition still comes from the quiver.
- While a character is DYING, a positive healing spell rescues them at **exactly 1 HP**, clears the death timer and sets ALIVE. Another player may use `administer <held healing potion> to <name>`. This consumes the potion. Neither method revives a DEAD or permanently dead character.
- With a free hand, `drag <first name> <exit>` moves you and a DYING/DEAD body through a valid exit. Locked doors and movement checks still apply. A group leader must leave their group first, preventing unwanted follower movement during rescue.
- Death continues to spill 10% of carried coins at level 10+. The starter-wealth safeguard suppresses coin drops below 10. Zero soul tether still leads to permadeath; the CRITICAL log record you reported is the intentional permanent-death audit, not a traceback.
- At a node, absorb XP and `advance`. HP and essence maximums grow, skill points accumulate, and one attribute point is awarded at levels 4, 8, 12, etc. Use `spend` for skills and `improve` for attributes. Techniques still unlock at 1/3/7. New eligible spells are also learned on reconnect after content updates.
- Tempest adds Wind Lash (1), Storm Mantle (4), Forked Lightning (8), Thunder Lance (12), Eye of the Tempest (18). Forked Lightning makes a separate hit/defense check against each non-civilian mob in the room; check the surroundings before casting.
- For NPC authors: use a mob attack named e.g. “dragon breath”, `attack_type: fire`, a speed and damage base/range. Its `effect_details` may specify `school: Arcane` and `damage_type: fire`. Elemental attacks, `spell` and `breath` use magical resolution; ordinary attacks use physical resolution. Existing CAN_HIDE/ambush behavior remains. This adds no dragon to the low-level slice.

## World, descriptions and administrator views

- From the plaza try `go march` and `go reedwater`; from the refuge type `return`. Full visible exit names work directly. Ambiguous abbreviations require more words.
- In an outdoor thunderstorm, listen for thunder, lightning and rain ambience. Ambient messages are periodic, not printed after every command. Indoor rooms do not receive outdoor weather messages. The existing seasons/day/night/weather effects remain.
- Lighting remains functional: LIT rooms, outdoor day/night darkness, lit carried/worn items, lit items on the ground, other characters' lights and magical light. A light inside a closed backpack does not illuminate the room. Test a dark room with and without a light.
- Coins weigh one stone per 100 Talons. Total recursive carried weight includes containers, contents and clothing. Might increases carrying capacity. Beyond half capacity, movement slows and announces the burden; a group matches its slowest burdened member.
- Create characters of all eight races. Race modifiers are still applied during stat assignment; `lore <race>` shows the numerical bonuses. All trait categories now work, including the Aelari/Veskar-specific options, scars, adornments and bearing. Existing descriptions/stats are not overwritten.
- `help hands`, `help movement`, `help destroy`, `help administer`, `help lore`, `emotes` and `emote <custom action>` provide guidance. There are 254 catalogued social gestures; existing command names retain precedence. Actions describe the actor rather than forcing another character's reaction.
- In the admin portal select **characters** or **character equipment**, choose one character, then open the detail sections. Equipment includes names, slots and GUIDs; inventory includes nested items, 50 per page. Live entities offers online-character selection and paged NPCs. Character stats/XP/position use current live values when available.
- Select an area and edit a room: its connected exits and connect button appear above the room fields. The visual map still loads one area at a time.
- Edit **lore articles** to publish lore. `topic` is the command key, `category` supports browsing, and `published` controls player visibility. Lore changes are read immediately and included in new build snapshots.
- Entity queries are bounded and page in batches of 50, maximum 100. Logging has its own search and older/newer pages inside a scrollable output. INFO logs rotate; warnings/errors/CRITICAL records persist in `warnings-errors.log`, downloadable from the portal. Combat hit, mitigation and parry/block calculations are logged at INFO for alpha testing.

## Automated tests and rollback

Run pytest only against a separate disposable PostgreSQL database, never your saved world. Follow `docs/QA.md` for the test database and `docs/VERIFICATION.md` for what was verified here. Keep the desktop gameplay observations coming: automated checks cannot certify enjoyable pacing or cloud capacity.

To roll back, stop the game, preserve the current database, and restore `pre-0.3.dump` into a **separate fresh database** alongside the saved old source revision. Keep the new and old volumes until you verify the restored world. Do not try to reverse migrations by deleting world data.

After local QA, push the imported branch through your authenticated GitHub setup:

```sh
git push origin HEAD:qa/desktop-0.3
```

Review it before merging to your main branch. This ZIP includes the Git history even if the connected GitHub integration cannot publish it.
