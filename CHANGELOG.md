# LanguageNut Bot — Changelog

## v2.0.0 — Major rewrite (fixes + optimization)

### Fixes
- **/homework crash fixed** — paginated view bypasses Discord's 25-field embed limit
- **/settings fully working** — every button now saves a real setting (with modals for numeric input) and persists per-guild
- **Autocomplete sped up** — 20s TTL cache means no more API spam on every keystroke
- **Multi-task /do** — comma-separated task list works (`123:0, 123:1, 456:2`)
- **/logs fixed** — now reads from `logs/bot.log` first
- **/reload** — accepts both short names and full dotted paths
- **Token refresh** — proper lock prevents race conditions on re-auth
- **Completed tasks** — auto-filtered from autocomplete

### Improvements
- Concurrent task execution using `asyncio.Semaphore` (configurable 1–8)
- Auto-retry with backoff (configurable 0–5 attempts)
- Single unified `commands/commands.py` (no more 4 fragmented files)
- Shared HTTP session with connection pooling
- Atomic config writes (no more corrupted configs on crash)
- Safer credential encryption with validation
- Precompiled regex for faster task routing

### Structure
- Merged `commands/core.py`, `commands/admin.py`, `commands/settings.py`,
  `commands/commands_profiles.py`, `commands/commands_settings.py` into a single
  `commands/commands.py`

## v1.0.3
- Fixed /homework embed crashing (Discord 25 field limit)
- Removed duplicate embed field logic
- Fixed indentation errors breaking command execution
