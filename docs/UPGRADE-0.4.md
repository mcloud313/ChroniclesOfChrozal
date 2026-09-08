# 0.4 alpha — professions, combat and tavern QA

## Upgrade the existing Bazzite installation

Keep the same project directory, Compose project name, `.env` and database volume. Do **not** run `seed`, `down -v` or delete the database. Stop the game and back up before applying migrations 020–021:

```sh
mkdir -p ../chrozal-backups
podman compose stop game
podman compose exec -T db pg_dump -U chrozal -d chrozaldb -Fc > ../chrozal-backups/pre-0.4.dump
podman compose exec -T db pg_restore -l < ../chrozal-backups/pre-0.4.dump
cp .env ../chrozal-backups/pre-0.4.env
chmod 600 ../chrozal-backups/pre-0.4.env
git status --short
git rev-parse HEAD
```

Use your configured database name and username if different. Check that the backup listing succeeds. Save your old commit and any uncommitted changes. Extract the release ZIP under Downloads, outside the running installation, then:

```sh
git fetch ~/Downloads/Chrozal-QA-0.4/chrozal-0.4.bundle qa/desktop-0.4
git merge --ff-only FETCH_HEAD
podman compose build game
podman compose run --rm game python scripts/manage.py init
podman compose up -d game
podman compose logs --tail=100 game
```

If your branch has diverged, preserve and merge your changes; do not reset hard. For a non-Git installation, copy the contents of the ZIP's `source/` over the existing project directory, retaining `.env`, logs and database volumes, then build/init/start as above. Hard-refresh the browser.

The migration preserves player and world data. It adds starter profession content to the existing Valian Coast only if Saltwind Strand is present at room 3. Custom worlds can use the builder configuration below. It does not regenerate the 100-room slice. Existing administrators and passwords remain unchanged.

## Gathering

Buy a profession tool at the Tideforge for 10 Talons. These apprentice tools each occupy one hand. Sheathe your weapon, hold the tool, and keep the other hand free. Tools inside backpacks do not count. Use `gather` to list the room's nodes.

| Profession | Starter resource | Location |
| --- | --- | --- |
| Herbalism | silverleaf | Saltwind Strand, 3 |
| Fishing | shore trout | Saltwind Strand, 3 |
| Mining | iron fragments | Serpent Road, 5 |
| Logging | driftwood timber | Serpent Road, 5 |
| Skinning | saltwind hide | Lantern Fields, 7 |
| Farming | barley grain | Lantern Fields, 7 |
| Hunting | game meat | Lantern Fields, 7 |

Example: `gather silverleaf`, `put silverleaf in traveler backpack`. The next harvest must refuse if both hands are occupied. `skin <slain beast>` additionally requires a skinnable corpse with an unused harvest claim, and uses the room's skinning node. Failed skinning consumes that corpse's claim.

Each attempt rolls d20 + skill rank / 5 (rounded down) + governing attribute modifier against difficulty (starter 8). Natural 1 fails; natural 20 succeeds. A failure yields nothing and exhausts the node. Success grants one item and one skill rank, capped at 100. A success has a 25%, 40%, 55%, 70%, then 85% depletion chance on successive uses; the five-unit starter capacity also imposes a hard maximum. Attempts take five seconds of roundtime.

Depleted nodes remain recorded in the database and appear as depleted in `gather`; they cannot be harvested. Starter cooldown is 15 minutes. After that, every actual world tick makes a rare recovery roll with a mean additional wait of one hour. This is random, not a guaranteed timer. Restarting does not refill nodes, reset usage, or grant offline recovery rolls. Resting XP nodes (`NODE`) are separate from gathering flags.

## Crafting

The Tideforge has stations and tools for smithing, alchemy, cooking, runecrafting and brewing. Recipes: wayfarer charm, coast salve, grilled trout, coastal rune, barley tea. `craft` lists requirements; `craft <recipe>` makes an attempt.

Hold the matching tool. Ingredients may be held or inside open owned containers, including nested containers with every containing lid open. Equipped gear, tools and nonempty containers are not consumed. Keep one hand available for the result. Every attempt uses the same skill-check formula, consumes the required ingredients, and takes six seconds; success yields one item and one skill rank. Existing blacksmithing rank counts for smithing checks. Grilled trout restores hunger; barley tea restores thirst. Coastal runes are crafting goods, not a new enchantment ability.

QA success, failure, closed containers, missing tools/stations, full hands, excessive weight, and inventory persistence after reconnect/restart. Production failures intentionally destroy ingredients; use disposable QA materials.

## Combat and taverns

Tide scavengers now initiate aggression. Do not idle in Lantern Fields assuming they are neutral. Hidden players are excluded from ordinary aggression and hidden-mob ambush selection. Safe rooms and XP nodes suppress NPC combat. Physical, ranged and spell hit narration varies by damage type and relative damage roll; criticals retain `CRITICAL HIT` and the existing crimson display. Hit and mitigation math still reaches participants and observers.

Mob attack authoring: elemental attack types or `spell`/`breath` use magical defenses. Set `effect_details.damage_type` to the element, and `effect_details.area_attack` to true to attack every living character in the room with separate dodge and mitigation checks. Such area effects can hit hidden characters. CAN_HIDE enables ambush behavior. No high-level dragon is added to the starter fields.

The tavern in room 2 supports:

- `cards bet 5`: deal five cards versus the house.
- `cards draw 1,3`: replace those numbered cards, then reveal and settle. You may replace up to three cards once.
- `cards stand`: keep your hand and settle.
- `cards`: rules and your saved unfinished hand.
- `dice 5`: roll two dice; a sum of 7 or 11 returns 15 Talons on a 5-Talon stake. Other totals lose the stake.

Cards use standard five-card poker rankings, including ace-low straights; suits do not break ties. A win returns twice the stake, a tie returns the stake. The dealer keeps pairs or better and otherwise keeps its two highest cards. Your discard choice provides the strategy. These are house games, not multiplayer poker tables.

Bets require level 10, a peaceful tavern, 1–10 Talons per hand, 30 seconds between new games and no more than 100 Talons staked per character per real UTC day. This build calls the currency Talons, consistent with the existing economy. Stakes debit before cards are shown; deck, hand and settlement are persisted. Reconnect or restart, return to the same tavern, and finish your hand. Repeated settlement must never pay twice. Tavern monetary records live in `tavern_ledger`; normal administrator log search still applies to combat and profession INFO output.

## Builder fields

Set room flags `<PROFESSION>_NODE` for gathering or `<PROFESSION>_STATION` for crafting (uppercase). They are available as checkboxes. Define nodes in Resource nodes with room, output template, profession, difficulty, capacity and cooldown (`respawn_seconds`). Usage, remaining units and depletion timestamp are server-managed. Define recipes with profession, output and ingredient-template quantities; matching station flags now determine usable stations, replacing the legacy single-room restriction. Tools use template stats such as `{"tool_for":["mining"],"weight":1,"value":10}`. Add `TAVERN` for gambling rooms.

Run automated tests only against a disposable PostgreSQL database. Never set `TEST_DATABASE_URL` to your live world. Continue the broader account, lighting, rescue, admin and progression checklist in UPGRADE-0.3.md.

## Additional combat audit in this release

`shoot` now provokes retaliation even when the projectile misses or is blocked. Physical attacks and offensive spells use the same engagement helper; a creature using an area attack keeps its primary target. Shots use the singular projectile name, so output reads **Your arrow critically hits… [CRITICAL HIT]**. The uppercase marker retains the crimson critical-hit styling. `ammo` reports ammunition by quiver, including whether each quiver is open, and works during roundtime. The character sheet also shows total ammunition and magical barrier.

| Training | Benefit |
| --- | --- |
| Bladed / piercing / bludgeon / martial arts | +1 melee attack rating per 25 ranks; +1 weapon damage per 20 ranks. Piercing uses the higher of piercing or bladed training, not both. Two-handed weapons now count. |
| Projectile weapons | +1 ranged attack rating per 25 ranks and +1 weapon damage per 20 ranks. |
| Shield usage | Adds 1 percentage point of block chance per 10 ranks to the shield's base chance, capped at 85%. |
| Armor training | Starts at 50% equipment armor effectiveness; reaches 100% at rank 50; adds 1 armor per 10 ranks beyond 50. |
| Warding | Adds 1 barrier per 20 ranks while a spell/item barrier is present. It does not create an uncast barrier. |
| Spellcraft / piety | +1 arcane / divine attack rating per 25 ranks; Mage Armor retains its spellcraft bonus. |

Weapon training is reflected in the displayed melee rating. Combat logs retain hit rolls and defenses, and now include base damage, damage dice, stat/training contribution and entity identifiers in engagement records. Physical resolution uses dodge, applicable parry/block, physical soak, armor and resistance; magical damage uses dodge, spell soak, barrier and resistance. Poison is mitigated as magical damage; bleed represents an existing wound. Ongoing poison/bleed ticks every three seconds, instead of depending on the server tick frequency, and retains its source for kill credit when the attacker is online.

The audit also repairs multi-part buffs, stat-buff contributions, legacy color placeholders in spell messages, natural spell names with spaces, area-spell targeting without a dummy target, and healing a DYING target through the actual cast pipeline. Buffs do not require hostile attack rolls. Sanctuary checks also cover hostile debuffs/control abilities between players.

Rogue QA: `use backstab <creature>` while hidden, `use garrote <creature>` while hidden, `use quick reflexes`, and `use apply poison`. These require learned abilities and their level/essence costs. Backstab's concealment check now happens before revealing the rogue. Garrote applies both bleed and silence. A poison coating can apply poison on a successful melee hit. Test perception, hiding, movement while hidden, lockpicking, searching and disarming. Creature theft now uses a persistent purse; stolen coins cannot also appear in its later death drop. Player theft remains level-10 gated and is prohibited in sanctuaries.

### Progression through level 30

Every class receives advanced techniques at levels 12, 18, 24 and 30, listed by `technique`. They cost 8, 12, 16 and 20 essence; the first grants a short defensive benefit and the third delays the enemy. Martial classes have distinct move names, such as rogue feint/shadow-cut/cripple/deathmark and ranger steady-shot/crossfire/pinning-shot/deadeye.

Seven casting classes gain a level-22 ward, level-26 area invocation and level-30 concentrated attack. Tempest gains **Thundercloud Aegis**, **Stormfront** and **Heavenbreaker**. The other casting classes receive corresponding themed abilities. Run `init` during the upgrade to add missing definitions; eligible characters learn them on reconnect. Existing edited definitions are retained. This extends ability progression; the authored 100-room world remains the level-1–20 slice.

### Magic QA sequence

1. Use two disposable characters outside a sanctuary, with a creature nearby. Record `score`, skills, armor and barrier.
2. Cast a damaging spell at the creature and then at the other character. Both victims should take the appropriate defense path, see math, and become engaged. Repeat in a sanctuary: hostile player actions must be refused.
3. Add an active barrier, then increase warding. Compare the same forced/test damage roll. Physical armor must not substitute for barrier.
4. Cast an area spell without a target name. Each target must receive an independent roll. For a creature breath attack, use a magical attack type and enable “Hits everyone in the room.”
5. Test healing while DYING: a positive heal rescues the character at exactly 1 HP. DEAD characters need resurrection rules, not ordinary healing.
6. Verify buffs, stance toggles, expiration, silence, poison/bleed ticks, concentration interruption, essence costs, roundtime and level gates. Restock test ammunition and consumables as needed.

## Builder improvements and loot controls

Entity lists now show ten concise entries per page with **Previous**, **Next**, **Page X of Y**, and a page-number field. Use **Inspect / edit** for full content. Nested quests, inventories and settings no longer expand into tall, narrow table cells.

Reference fields search by name and display a readable name plus its identifier; you do not need to memorize IDs. This covers rooms, areas, creature/item templates, loot tables, factions, recipe outputs and NPC schedules. Item creation starts with a type dropdown and reveals the relevant damage, ammunition, armor, container, wearable or consumable fields. Room spawners and recipe ingredients use named selectors. Quest objectives have kind, instruction, quantity and named target controls. Advanced properties remain available for unusual authored behavior.

**Tide scavengers originally have no item-drop entries.** Their coins come from the creature template's **Maximum Talons**, independently of the item loot table. Set it to zero to disable coin drops; otherwise a new creature's purse is randomly initialized from zero to that maximum. To add items, create **mob loot table** entries, choose the creature and item by name, and set drop chance between 0 and 1. Publish changes. Existing creature purses may already have been rolled, but a maximum of zero suppresses death coin drops.

**Complex exits:** create a named entrance such as `ledge`, `narrow hole`, or `river crossing`, and enable “Complex entrance.” Players use `go ledge`, etc. Configure the required skill, difficulty, failure HP loss, prone toggle, failure text and roundtime independently. A complex entrance must use a name rather than a compass direction. Ordinary compass exits continue to work as before.

**Doors and traps:** the exit editor has separate door, open/closed, lock, key-code, pick difficulty and trap controls. Keys carry matching codes in their item properties. Players can open/close, lock/unlock with a held key, search, lockpick and disarm. Both sides of an unambiguous paired door share open/locked state; if there are several return doors, specify the linked reverse exit name. Traps are per exit direction. Failure can trigger and consume a trap; search reveals an active trap before disarming. Crossing failures can leave party members behind.

**Delete an exit:** open its editor, type `DELETE`, and press **Delete this exit direction**. This deletes only that direction and records an audit entry. Delete the reverse separately if desired, then publish the world. A concurrently changed exit must be reloaded before deletion.

Weather ambience, sunrise and sunset remain active for outdoor characters. The time command, dusk and midnight now describe the two moons' phases, calculated from the saved calendar.

## Validation and limits

The full automated suite passed 52 tests, including the original 60 class-combat samples. Additional command-level checks exercise natural spell names, area casting, backstab, garrote, ammunition, NPC retaliation, training, spell resolution, healing rescue and level-30 techniques. Desktop and 390-pixel mobile browser checks found no JavaScript errors or document overflow; screenshots were inspected for the paginated builder and forms.

These checks used the disposable PGlite PostgreSQL-compatible adapter in this workspace. Native PostgreSQL on Bazzite, multi-player balance and 100-player hosting capacity still require your environment tests. Back up your real database before upgrading. This ZIP contains a Git bundle; it has not been pushed to GitHub from this session.
