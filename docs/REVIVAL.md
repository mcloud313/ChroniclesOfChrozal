# Chrozal revival

The supplied ZIP matches GitHub main at `3c5c9bc` (October 8, 2025). The PDFs describe a Django Worldpainter absent from that checkout; the repository contains an unfinished FastAPI/React portal. No PostgreSQL dump was supplied, so historical authored rooms and player records cannot be recovered from source alone.

## Playable alpha

The retained asyncio engine now runs behind one FastAPI process with an authenticated browser client and builder. The active entry point starts no Telnet listener. The old React source remains only as reference.

The optional fresh-world seed creates 15 connected rooms around Port Valis and the Valian Coast, nine chapters leading from level 1 to 10, eight hostile enemy templates, gathering, two recipes, a scheduled resident and a uniquely claimable starmap fragment. Mira and these chapters are proposed new content inspired by the supplied lore, not recovered database content.

All eleven classes receive a resource-free basic technique at level 1, a signature at 3 and a finale at 7. Enemy wind-ups support bracing and retreat; safe nodes restore resources. Crafted coast salve heals with `treat`. Quest rewards feed the XP pool, which absorbs at nodes before `advance`. A common assignable starting stat array replaces unlimited random rerolls; level gains are deterministic.

The browser HUD shows HP, essence, room/exits, recovery, level, XP pool, inventory, time, weather and needs. Social commands remain available during recovery. See [playtest guide](PLAYTEST.md) and [Bazzite setup](BAZZITE.md).

## Persistence and building

PostgreSQL stores characters, stats, equipment, item locations (including containers and banking), quest objectives/rewards, journal, resource depletion, recipes, schedules, relic ownership and authored definitions. Periodic checkpoints additionally save NPC instances/health/death timers/effects, area weather, game time and active characters. Graceful shutdown saves the world; ordinary container restarts retain the database volume.

Checkpoints default to 30 seconds. A hard crash can lose changes since the last completed checkpoint; world checkpoints now commit as one atomic, set-based database transaction. Transactional quest completion, crafting, bank transfers and salve use commit their relevant database changes together. Groups, sockets, current combat targets and in-flight spell casts are transient and are not resumed after a process restart. This is persistent play, not crash-proof execution replay.

The administrator can inspect entity tables and live entities, create/edit allowlisted definitions, search and paginate, inspect recent logs and persistent audit records, publish without disconnecting players, and save/restore named build states. Edits reject stale row versions. Complex fields currently use JSON editors; a visual map editor remains future work.

Build states contain authoring definitions. Restoring merges saved rows, retains entities added later, and preserves player progress, depleted resources and claimed relics. It is not a destructive database rollback. Runtime checkpoints preserve NPC damage across publication. Use database backups for disaster recovery.

## Repairs and access controls

Removed source credentials and automatically provisioned default accounts. Existing installations need an explicit legacy-account cleanup and credential rotation; old Git history still contains credentials. Fixed group acceptance/leader association, username state handling, swallowed save failures, respawn schema/fallback, inventory reload caches, bank item location constraints and bank coin transfers. Repaired a missing brace that nested most ability definitions inside Smite, restoring 34 top-level abilities, and normalized Monk/Paladin definitions.

Opaque expiring cookie sessions, exact Origin checks, admin authorization, bounded password hashing, input/output limits, one connection per account and a 100-connection ceiling protect the web path. Gameplay recovery is checked at receipt and dispatch; commands are not queued for automatic execution. The server calculates damage and state. Browser scripts can still imitate legitimate input: these measures reduce abuse, not prove a human is playing. Do not add disruptive CAPTCHA to normal roleplay.

## Remaining boundaries

This is a development vertical slice, not a finished 1.0. The automated class test accelerates travel and time; human testing must judge pacing, challenge, clarity and fun. Signatures differ, but the level-7 finale shares a damage model. The retained legacy spell, PvP, economy and equipment systems need broader balance/regression coverage. Safe-room/PvP consent rules need a dedicated pass before public competitive play.

NPC behavior includes schedules/dialogue, combat telegraphs and optional patrol/flee flags. Faction standing, offline mail, stalls, enchanting and infusion are implemented. Deeper professions, seasonal resource quality, relic powers/provenance and communal projects remain future expansions. The starmap fragment currently provides discovery and ownership, not a complete legendary power tree. Database guards prevent duplicate creation for designated relic templates; legacy duplicates require an import audit.

Account email is not verified. Password reset, OAuth, granular builder roles and moderation workflows are pending. Keep this trial invitation-only. The runtime log panel is bounded and temporary; audit records persist and container logs rotate.

100 simultaneous players remains a hardware acceptance target. Keep one authoritative server worker. The included load harness measures browser-protocol speech/HUD traffic; it does not certify mixed combat, login bursts or a Droplet. See [verification](VERIFICATION.md) for actual evidence.

The expanded scope and exact roadmap acceptance status are tracked in [ROADMAP_STATUS.md](ROADMAP_STATUS.md). Use [QA.md](QA.md) for the complete test procedure.
