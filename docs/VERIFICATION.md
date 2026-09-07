# Verification record

This branch is undergoing expanded validation. It is not a signed-off 1.0 release.

- Python 3.12 compilation and the focused regression suite passed.
- The expanded 20-test integration/regression run passed (199.57 seconds), including eleven level 1–10 class arcs, permanent death at zero tether, cleric XP payment, offline mail, market settlement, enchanting and infusion persistence. It predates the final housing-room addition.
- Real Chromium desktop and 390px mobile checks reported zero JavaScript errors and no horizontal overflow. Firefox/Bazzite must be checked on the target desktop.
- PostgreSQL integration ran locally using embedded PGlite with an asyncpg protocol adapter and one connection. That adapter has exhibited protocol errors under load; it is not a substitute for native PostgreSQL 16.
- The latest 100-player local test reached 100 simultaneous players but recorded one failed client and an autosave/protocol error. This is a failed acceptance run, regardless of otherwise improved latency. The JSON report records the failure.
- A native PostgreSQL 16 GitHub Actions workflow is included. Its outcome must be recorded after execution.

The tests accelerate node time and move characters directly for objective setup. They test real combat handlers, quest rewards and persistence, but do not measure hundreds of hours of live progression or prove that every class is fun. Use QA.md for remaining manual/release checks.
