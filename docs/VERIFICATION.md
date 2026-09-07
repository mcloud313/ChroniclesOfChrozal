# Verification — 0.2.0-alpha

This is a development QA build, not a signed-off 1.0 release.

## Executed

- Full integration/regression run: **35 passed in 131.97 seconds**. It covers database migration, authentication, administrator denial, build-state restore, hot publication, NPC checkpoints, item/bank/economy persistence, soul-tether permadeath, cleric payment, password reset, notice limits/rewards, movement, recovery supplies, ranged ammunition and class combat.
- Updated content/account/party/combat suite: **5 passed in 79.01 seconds**, including a forced successful bow hit, rejection of ammunition access from a closed quiver, real-container sheathing and immediate nested bank withdrawal.
- Additional party-notice regression: **1 passed**. Both leader and follower receive visit progress, must return together, and cannot duplicate completion rewards.
- Class combat sample: **60 encounters**, covering all twelve classes at levels 1, 5, 10, 15 and 20 using ordinary stats and no mid-fight healing. All completed with surviving characters. This exercises the technique/AI loop; it does not simulate a complete natural level-1-to-20 campaign or establish enjoyable pacing.
- Chromium desktop and 390-pixel mobile: **zero JavaScript errors and no horizontal overflow**. Browser checks cover the north exit button, typed south, character sheet, abrupt close/reconnect with resumed character, administrator map/room editing and creation-wizard navigation.
- Python compilation, JavaScript syntax checks and Git whitespace checks passed.

The old chapter test used direct room assignment and instant healing. It was removed along with the obsolete chapter/recover handlers. Current movement and supply tests issue actual commands; the browser test clicks the actual north button. Combat samples still accelerate roundtime and set test levels deliberately.

## Environment and remaining acceptance

Database tests here use embedded PGlite with an asyncpg wire-protocol adapter and one connection. They test PostgreSQL SQL semantics but are not a native PostgreSQL 16 run. The adapter produces noisy protocol failures when SQL errors occur; those failures were diagnosed and corrected, not counted as passes. Test dependencies also emit two deprecation warnings unrelated to game behavior.

The previous build's 100-client speech/HUD benchmark remains in load-test-result.json as historical evidence. It was **not rerun as a mixed-workload capacity certification for 0.2**. Native PostgreSQL, 100-player sustained combat/crafting traffic, CPU/memory/tick-lag measurements, and a restored-backup trial on the intended host remain release gates. No Droplet was deployed.

SMTP delivery, real-device mobile browser suspension, full party campaigns, economic pacing and player enjoyment require local testing. Email verification and command limits do not make a browser game automation-proof. Existing accounts are grandfathered as verified; fresh public registration requires SMTP verification. One account can have one active play session, with five minutes of vulnerable link-loss persistence.

Warning/error records append to warnings-errors.log in the persistent log volume; informational records rotate. The archive has no automatic deletion policy. Include relevant excerpts with bug reports and manage its retention with backups as the game grows.

The upgrade is additive and preserves the previous schema and records. The expansion is repeat-safe and adds 85 rooms to the 15-room starter, plus five boards/areas. Player housing and builder-created rooms can make the total exceed 100. Existing character stats are not rerolled. Existing low-level claimed relic records are retained; the new slice awards no relics below level 50.
