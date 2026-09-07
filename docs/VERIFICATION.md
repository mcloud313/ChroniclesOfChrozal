# Verification record

This is a development QA build, not a signed-off public 1.0 release.

## Passed locally

- Python 3.12 compilation; Compose YAML parsing with duplicate-key detection.
- Full 21-test integration/regression suite: **21 passed in 206.80 seconds**. Includes all eleven class arcs from level 1 through 10, auth/admin boundaries, builder conflicts/audit, live publication, saved-build restore, NPC checkpoints, inventory/banking/salve persistence, zero-tether permadeath, cleric XP payment, mail, market settlement, enchanting, infusion, housing and fractional hunger/thirst checkpoints.
- Focused regression suite after the final combat corrections: **11 passed**. Two additional checks cover natural d20 outcomes under modifiers and weather damage/sanctuary protection.
- Real Chromium desktop and 390px mobile: **zero JavaScript errors, no horizontal overflow**. The visual map opens and clicking a room opens its editor.
- Local browser-protocol load: **100 simultaneous players, 500 command samples, zero client failures**, median **7.62 ms**, p95 **882.92 ms**, maximum **965.42 ms**. Server logs contain no ERROR/CRITICAL/Traceback entries. See load-test-result.json. Logout fixtures were retained until saves completed.

## Important limits

Database tests used embedded PGlite with an asyncpg wire-protocol adapter and one connection. They exercise PostgreSQL SQL semantics, but are not native PostgreSQL 16 or a Droplet benchmark. Earlier runs exposed an integer/fractional-needs schema bug, fixed by migration 011; the adapter also mishandled the resulting error responses. The failed runs are not counted as capacity success.

The load harness measures authenticated speech broadcasts and HUD delivery, excluding HTTP login throughput and sustained mixed combat/crafting traffic. Its p95 exceeds the aspirational 250 ms target in this environment. Native PostgreSQL, CPU/memory/tick-lag measurement, sustained mixed-load and backup restore remain release gates.

The class test accelerates node time and moves characters directly for objective setup. It tests actual combat handlers, quest rewards and persistence; it does not prove enjoyable pacing, validate every retained legacy spell or simulate hundreds of real play hours.

Bazzite/Firefox testing must be performed on the target desktop. Docker/Podman images and native PostgreSQL were not executed here. A PostgreSQL 16 CI workflow with a 100-client load stage is included but has not run: the GitHub connection denied repository writes, so the branch could not be published in this session.

## Delivery provenance

The local branch `revival/web-realm` is based on the supplied repository's main commit `3c5c9bc`. The delivery contains current source and a Git bundle of the new commits. Uploaded source/PDF originals are retained. No previous world database was supplied or overwritten. No cloud service was deployed.
