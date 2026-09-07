# Bazzite whole-project QA

Use a disposable local world. Follow [BAZZITE.md](BAZZITE.md) first. This is a release-candidate test plan; a checklist entry is not a claim that it has passed on your desktop. Record the branch commit, class, race, command, expected result, actual result, and logs with each failure.

## Provision the two accounts

After initializing and seeding, run:

```sh
podman compose run --rm game python scripts/manage.py qa-accounts
```

Choose two different passwords when prompted. The command creates `chrozal_admin` with administrator privileges and `chrozal_tester` with a level-1 character for each of the twelve classes, including Runewarden and Tempest. It refuses to overwrite existing accounts. No public default password is embedded in the project.

Sign in at `http://localhost:8000`. Use separate Firefox profiles or a private window to keep administrator and testing sessions separate. Only one play connection per account is allowed. Administrator and player pages share one origin.

## Automated tests on native PostgreSQL

Create a separate empty database; never use the seeded playtest database for the suite:

```sh
podman compose exec db createdb -U chrozal chrozal_qa
podman compose run --rm game sh -c 'pip install --user -r requirements-dev.txt && TEST_DATABASE_URL="${DATABASE_URL%/*}/chrozal_qa" python -m pytest -q'
```

If the container image does not include development requirements in a later release, use the Python/Distrobox instructions in README with the same disposable database. Integration tests seed their own world, create accounts and alter world state. Start fresh for each independent run.

## Access and browser behavior

- Sign out: `/api/admin/catalog` must reject access. As `chrozal_tester`, the builder link is hidden and administrator APIs return 403. As `chrozal_admin`, catalog, runtime entities, logs and map work.
- Open a second play tab under the same account: the second connection is rejected. A normal logout/reconnect preserves the character.
- Try Firefox desktop and a narrow phone-sized window. Check HP, essence, tether, attack/armor, roundtime, date, seasons and weather. Long descriptions should wrap without horizontal page overflow.
- Send markup such as `<script>alert(1)</script>` in speech: it must appear as text and never run. Paste multiple newlines/control characters: malformed protocol input is rejected. Repeat an attack during recovery: it must be rejected rather than queued.
- `say`, `emote`, `pose` and `look` should remain usable during recovery. Repeated `brace` must not shorten an attack's recovery. Browser automation is still possible; these are server-enforced limits, not human verification.

## Creation and roleplay

Create additional characters using `new`. Try every race and pronoun option, especially fur, shell, scale, tail and beard traits. Inspect the resulting description with another character. Look for missing traits, contradictory hair choices and awkward grammar. The system describes appearance without assigning personality.

Assign the rolled scores differently across two characters. Scores use 4d6+1 before racial modifiers; 25 is exceptionally rare. Verify descriptions, stats and equipment after reconnect and server restart. Test invitations, acceptance, group leadership transfer and movement with a member in another room or still recovering.

## Levels 1–20 and combat

Play every class through [PLAYTEST.md](PLAYTEST.md), including Runewarden and Tempest (`etch`, `aegis`, then `finale`). Record elapsed time, deaths, retreats, waiting, travel and whether abilities create meaningful choices. The automated arc accelerates time/travel and does not establish that pacing is fun.

At the Tideforge, `list`, buy a wayfarer dagger, and compare `attack <enemy>` with a coast greatsword. Inspect the actual roll, attack rating, defense, damage and recovery. A miss or parry must retain weapon recovery. Check armor mitigation and armor movement penalties. Test bows/ammunition with authored ranged equipment; the Ranger technique is a separate resource-free class action.

Spellcasters learn additional invocations at levels 5, 9, 12 and 18 (depending on class). Use `abilities`/the retained ability help to inspect their internal names and targeting syntax. Test interruption, insufficient essence, target leaving, death during a cast, and the full cast/recovery time. Compare fire and lightning damage outdoors in rain against clear weather. Do not infer full legacy spell balance from the class-kit test.

## Soul tether and long progression

Tether decreases on releasing a dead character. At zero, status becomes PERMADEAD; the character must disappear from selectable characters and must not respawn on reconnect. Possessions and records must remain consistent. Test only sacrificial fixtures.

A living cleric at a peaceful node can `tether self` or `tether <character name>` to see the absorbed-XP cost. Repeat the exact command with `confirm` to pay it. The caster pays; the target gains one point, capped at ten. Try inadequate XP, another class, a target in another room and a permanently dead target. Verify XP/tether after restart.

XP enters a pool and absorbs only at nodes, where PCs can socialize. At the default 5 XP/second, level 75 requires 10.8 million cumulative XP: 600 hours of node time alone, plus adventuring. Each level after 75 costs 18% more than the previous increment; 99 is the cap. This deliberately slow baseline should be reviewed after the first real playtest.

For expensive or destructive QA, sign OUT of `chrozal_tester`, then change only its test fixture:

```sh
podman compose run --rm game python scripts/manage.py qa-set Cleric --level 20 --surplus-xp 50000
podman compose run --rm game python scripts/manage.py qa-set Warrior --level 10 --tether 1 --dead
podman compose run --rm game python scripts/manage.py qa-set Mage --level 99 --surplus-xp 500000
```

These are explicit test-account commands, never production progression. They retain quest history and inventory. Use a fresh test database for a completely fresh playthrough.

## Calendar, weather, NPCs and professions

- Use `time`: check named day/month/year and seasonal weather, including autumn. Check day/night outdoor darkness, racial vision and light sources. Confirm dates/weather survive restart.
- Have the administrator edit a room's `MUD` or `SNOWY` flags and publish. Movement should take longer. Ordinary outdoor weather penalties must not apply inside a building.
- Find Mira by day and night. Test a mob with `PATROL` and one with `FLEES` at low health. Verify they remain within their area, avoid nodes, and retain their location/health after a checkpoint and restart.
- Gather silverleaf and mine iron; deplete a node, restart, and wait for regrowth. Check gathering/profession rank gains. Kill a skinnable beast, `skin <name>`, then try again: only one harvest is allowed for that corpse.
- Craft salves and charms, test insufficient materials, full inventory/carry weight, `treat`, and reconnect. Materials must not duplicate after interrupted requests. Claim the starmap fragment once; a second claim must fail.

## Economy and community

- Buy/sell at the Tideforge; verify coin, stock and item state together after reconnect/restart. Try zero/negative amounts and repeated requests. A purchase/sale cycle must lose coins, including high bartering skill.
- Deposit/withdraw coins and items at the tavern bank. Test insufficient balances and containers. No item should exist in both bank and inventory.
- Use `mail` to send to a character ID, including an offline recipient. Use the character ID shown in the administrator’s character catalog. Test reading somebody else's letter and rejecting item attachments. Mail carries letters only.
- Complete a notice-board contract and inspect `reputation`. Configure a quest, shop entry or exit with a faction threshold; check both sides of the gate and repeat turn-in to ensure no duplicated rewards.
- `market sell 100 <item>`, buy it using another account, and test cancellation. The seller receives proceeds minus tax, even offline. Two buyers must not receive the same item.
- `home buy`, `home describe <text>`, and `home visit <character id>` test the first housing charter/description system. Use `home enter` to enter the persistent room and `out` to leave; drop and retrieve furnishings/items and check them after restart.
- At a node with two PCs, alternate `tales <sentence>`. There is no XP/coin reward and one player cannot take consecutive turns.
- `enchant <item>` at the Tideforge spends coins; check rank cap and persistent bonuses. At level 99, `infuse <item>` spends surplus XP above the cap threshold, with increasing cost and a rank cap. Reconnect and check the actual damage/armor bonus.

## Builder and persistence

Save a named build state. While a player remains connected, change a room description and publish. HP, equipment, position and NPC wounds must survive and the connection must remain usable. Restore the named state: saved definitions return, later-created entities and player progress remain.

Open the visual map, drag a room and save its layout; click a room to edit. Connect rooms through the exits catalog. Test stale edits from two tabs: the second edit should report a conflict. Inspect audit entries and server/error/public-chat rotating logs.

Drop an item, put another inside a container, bank a third, complete a quest, wound a mob and change the game time. Wait for the autosave, restart the game service and check every state. The world checkpoint is a single transaction. In-flight casts, sockets, groups and current combat targets are transient; a hard crash can lose progress since the last checkpoint.

## Capacity, backups and release gate

Run the 100-client harness against a disposable local deployment, then repeat on the eventual Droplet. Include a sustained mixed workload and monitor CPU/memory/tick lag, not just speech acknowledgment. See DEPLOYMENT.md. A short local harness does not certify cloud capacity.

Back up using `pg_dump`, restore into a NEW database, and repeat login/inventory/bank/quest/build checks. Keep a copy outside this computer. Do not use `podman compose down -v` on a world you want to retain.

Do not declare 1.0 until the roadmap traceability checklist, native PostgreSQL tests, Firefox QA, backup restoration, mixed-load soak and human class playtests have passed with recorded evidence.
