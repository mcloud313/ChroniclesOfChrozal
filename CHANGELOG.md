# Changelog

## 0.2.0-alpha — desktop QA iteration

Based on the previous delivered commit, `5303dbf`.

- Fixed short/long compass commands and exit buttons. All directions now share door, lock, hazard and destination checks.
- Added a Tempest class and Kaiteen, Aelari and Veskar race choices; filled the original four class descriptions. Added level-12/18 spells for magical classes.
- Replaced fixed character stats with rerollable 4d6+1 scores. Natural 25 probability: 1/1296 (0.077%) per attribute, before racial modifiers; rerolls wait two seconds.
- Removed player-facing recover, chapter and relic-claim shortcuts. Recovery now requires resting, food and water; nodes accelerate regeneration. Notice-board quests have ten shared daily notices, one active contract per character, and party contracts for two or three adventurers.
- Corrected bow hand occupancy, ammunition template access, weapon equip defaults, lock/door data disagreement, environmental damage and container trap calls. Added stable held-hand labels and a hold command. Sheathing now puts weapons in real open containers; bank withdrawal reconstructs container contents immediately.
- Standardized wealth remains 125 Talons. Player gifts/stalls unlock at level 10; mailed attachments are disabled; early dropping and starter death-estate transfers are restricted.
- Added colored, text-safe browser output, auto-scroll preference, character sheet, online roster and safe Disconnect. Added a five-minute link-loss reconnect window and heartbeats.
- Protected both the administrator page and its static assets. Added structured JSON fields, flag checkboxes, room/item creation steps, per-area maps, room-exit panels and room destination choices.
- Added detailed live player inspection, connection events, kill counters, economy aggregates and an append-only warning/error archive alongside rotating informational logs.
- Added expiring one-use password reset/email verification codes. Public registration requires configured verification email delivery. Existing accounts retain access.
- Added persisted area climate and limited non-desert BLAZING weather to rare midsummer events.
- Added an optional, repeat-safe 85-room expansion with five areas, level 4–20 opponents, boards, supplies, scheduled shopkeepers, traversal shortcuts and a trapped lockbox. Starter plus expansion totals 100 rooms before player housing or builder additions.

This is an alpha QA build. Human playtesting, native PostgreSQL capacity testing and release-roadmap acceptance remain necessary; a room count or passing combat sample does not establish a finished 1.0 world.
