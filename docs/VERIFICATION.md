# Verification — 0.3.0-alpha

- Full automated suite: **46 passed in 181.65 seconds**, including 60 class combat encounters across 12 classes and levels 1, 5, 10, 15 and 20.
- Ten new regression scenarios cover gathering with a wielded dagger, real container transfers/sheathing, confirmed destruction/relic refusal, overflow repair with GUID preservation, restart persistence, DYING rescue and dragging, enemy hit/miss/critical and fire-breath attacks, administrator/password gates, race trait creation, lighting/weather, progression, registration/verification, and idempotent initial-administrator setup.
- Desktop Chromium and 390×844 mobile viewport: zero JavaScript errors and no horizontal overflow. Checked typed movement/buttons, reconnect, safe quit, character sheet, single-character inspection, room exit buttons and creation wizard. Screenshots were inspected.
- Python compilation, JavaScript syntax and Git whitespace checks passed.

The tests use disposable PGlite through an asyncpg wire adapter with one connection; they are not a native PostgreSQL or Bazzite run. Two dependency deprecation warnings remain. An initial browser-harness cleanup attempted to delete a fixture account that owned starter items; the database correctly refused orphaning those items. The final harness discards its entire disposable database and completed successfully.

This is an alpha, not a 1.0 or 100-player capacity certification. No cloud deployment or new load benchmark was performed. The old load-test result is historical. SMTP delivery, real-phone suspension, natural campaign pacing and restored-backup QA remain local checks. Use `docs/UPGRADE-0.3.md` for the Bazzite sequence; never point automated tests at your saved world.

Migration 019 is additive, grants equipment only into vacant slots, and leaves existing accounts and character stats intact. The server retains the level-20 world. INFO/combat logs rotate; warnings, errors and intentional CRITICAL permadeath events append to the persistent warning archive.
