# Roadmap to 1.0: traceability

Source: supplied **Roadmap to 1.0.pdf**, September 26, 2025. Its “completed Django portal” is absent from the supplied source; this branch implements a FastAPI portal. Historical status labels are not treated as test evidence.

“Implemented” below means code exists in this branch; consult VERIFICATION.md for tests actually run and QA.md for acceptance procedures. It does not mean a public 1.0 release is certified.

| Roadmap item | Branch implementation / remaining acceptance |
|---|---|
| Core engine, PostgreSQL, builder | One authoritative asyncio world; authenticated FastAPI builder and web client; versioned migrations |
| First Valian Coast content | 15 seeded rooms, nine chapters, level 1–10 arc; human pacing review required |
| New classes | Original ten classes repaired, Runewarden added; class kits and additional spells |
| Ranged combat | Existing ranged weapon/ammunition resolver retained; Ranger class technique is a separate action; wider equipment QA required |
| Light/dark, ambient scripts, needs | Retained; day/night, racial vision and needs shown/testable |
| Time/day/night | Persistent named calendar, 26-hour days, months/seasons; full date in HUD |
| Weather changes gameplay | Outdoor movement/visibility, wet fire/lightning modifiers, mud/snow recovery; autumn name mismatch fixed |
| Broken grouping | Invitation ID and leader association repaired; movement filters absent/recovering members |
| Offline mail/messages/items | Persistent inbox, recipient access checks, postage and optional loose-item transfer |
| PvP targeting | Existing player targeting retained; safe-room coverage across all attack types still needs release QA |
| Faction/reputation | Persistent standings, quest rewards and gates for quests, vendors and exits |
| Gathering/crafting | Resource depletion/regrowth, mining/herbalism, skinning claims, alchemy/blacksmithing rank gains, recipes and salves |
| Rotating logs | Separate bounded server/error/public-speech logs plus persistent builder audit |
| Integration tests | Startup/migration, auth, builder, persistence, class arc and economy/soul tests; see actual results |
| Database-driven balancing | Existing ability/item/mob templates plus class_kits, validated progression/combat/terrain/tether balance_rules, recipes and faction/quest gates. A complete audit of every retained legacy subsystem remains a release task. |
| Telnet to WebSocket | Active server starts only HTTP/WebSocket; authenticated sessions and exact Origin checks |
| Web/mobile client | Responsive client with HUD and command history; desktop/mobile browser checks |
| Endgame item infusion | Level-99 surplus-XP sink with permanent item damage/armor bonuses and capped escalating ranks |
| Advanced NPC AI (aspirational) | Schedules, authored dialogue, telegraphs, optional patrol and low-health flee flags; not a general planning AI |
| Player housing (aspirational) | Persistent purchasable home room, editable description, owner entry/exit and saved items; deeper furniture interactions remain an expansion |
| Player-driven economy (aspirational) | Fixed-price escrow stalls with cancellation, offline proceeds and tax; timed bidding auctions remain an optional expansion |
| Visual map editor (aspirational) | Room graph, draggable saved layout and click-to-edit; exit connections use the catalog form |
| Enchanting (aspirational) | Coin-funded permanent equipment ranks at the Tideforge; deeper recipes/materials remain a design expansion |
| Tavern games (aspirational) | Shared Tales alternating-player story game, no farming rewards |
| Quest system | Database definitions, builder support, objective log, acceptance, turn-in, journal and reputation |
| Runewarden | Eleventh playable class with etch/aegis/finale and Stone Memory spell |

## Additional requirements from this session

- Zero-tether release permanently retires the character; clerics can restore living tethers at absorbed-XP cost.
- XP soaking remains node-only. Default curve requires 600 node-hours to 75 and exponential increments to maximum 99.
- Weapon/cast/terrain roundtime, attack rolls, attack ratings and armor are visible. Misses and parries no longer shorten weapon recovery.
- Race-specific description generation includes every configured trait without assigning personality.
- Explicit QA-account provisioning creates an administrator and one testing character per class; no default passwords.
- Atomic world checkpoints, retained database volumes and live build publication support persistence without resets.
- 100-player mixed-load and native Bazzite/Firefox validation are release gates, not yet a cloud-capacity certification.

A truthful 1.0 signoff still requires the incomplete rows to be resolved or explicitly removed from release scope, and the acceptance checks to pass. Do not relabel these as complete merely because the original roadmap marked earlier phases complete.
