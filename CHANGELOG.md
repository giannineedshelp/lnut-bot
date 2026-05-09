# LanguageNut Bot — Changelog


## v2.0.3 - Code deduplication, environment cleanup, Pylance fixes

### Fixed
- **GUILD_ID constant redefinition** - replaced try/except with conditional assignment;
  Pylance no longer flags reportConstantRedefinition
- **Pylance missing-import warnings** - added .vscode/settings.json pointing to correct
  Python interpreter; suppressed reportUnknown* diagnostics (discord.py/aiohttp lack type stubs)

### Improvements
- **Deduplicated `_pct` and `_is_done`** - moved shared helpers from `automation/discover.py`
  and `commands/commands.py` into `utils/helper.py`; both modules import from single source
- **Removed unused packages** - `requests` and `aiofiles` are not imported anywhere;
  dropped from `requirements.txt`
- **Cleaned `.env`** - removed `COMMAND_PREFIX` (bot uses hardcoded `"!"`)
- All files continue to compile clean (py_compile) and pass full import chain test

## v2.0.2 — Setup ordering fix + code quality

### Fixed
- **`setup()` function misplaced** — defined before `BotCommands` class at module level; moved to end of file after the class definition. While Python's late binding prevented a runtime crash, static analyzers flagged this as a `NameError` risk, and it broke IDE navigation/autocomplete in VS Studio
- **PEP8 blank-line violations** — added missing blank lines between `quick_do` and `do_task` methods, and before module-level function definitions

### Improvements
- All `.py` files compile clean and import without errors
- Full code review completed: no syntax errors, no dead code, no async/await issues remain
- Consistent file structure with `setup()` following the standard discord.py pattern (last function in the module, after all class definitions)

## v2.0.1 — Hotfix: critical runtime errors + Windows compat

### Fixed
- **`task_autocomplete` NameError** — moved autocomplete function definition before `BotCommands` class so the decorator `@app_commands.autocomplete(task=task_autocomplete)` resolves at class-creation time (was crashing on module import)
- **`/do` command not registered** — orphaned decorator at line 1076 had no function body; connected it to the undecorated `do_task` method so `/do` actually works
- **`os.execv` crash on Windows** — `os.execv` is Unix-only; replaced with `subprocess.Popen` + `os._exit(0)` for Windows-compatible restart
- **Dead code after `raise`** — removed unreachable `await bot.start(TOKEN)` in `main.py` that followed a `raise` statement
- **Missing `.env` vars** — added `GUILD_ID` and `OWNER_ID` to inner `.env` (were only in `.env.example`)

### Improvements
- All Python files pass `py_compile` and import without errors
- Cleaner separation: `task_autocomplete` is now a module-level function alongside other helpers

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

