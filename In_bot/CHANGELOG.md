# Changelog

## v2.1.1 (2026-05-14)

### Added
- `/hub` command with all actions: Login, Logout, Farm, Homeworks, Leaderboard, Health, Settings, Help, Refresh
- Admin panel (`/admin` or hub button) with Sync, Reload, Logs, Update, Restart, Shutdown
- Owner-only admin commands with proper permission checks
- Full `lnut_api.md` documentation with all discovered endpoints

### Fixed
- **Login broken** — `LanguagenutClient.login()` now uses `"pass"` param and looks for `"newToken"`
- **Account Health shows "Not Logged In" for banned accounts** — now properly detects bans with unban timer
- **Voice channel status** — cleaner names (🟢 Online, 🌾 Farming, 🟡 Idle, 🔴 Offline)
- **Rate limiting (429) on status channel** — exponential backoff with jitter, fewer API calls
- **Old cached commands causing CommandNotFound** — clears old commands before syncing
- **Termux startup crash** — removed `cryptography` dependency entirely

### Removed
- Admin credential encryption approach (dead code, permanently deleted)
- `cryptography` dependency — no longer needed anywhere

## v2.1.0 (2026-05-13)

### Added
- Admin credential storage with Fernet encryption
- Teacher/admin login, ban/unban, student management commands
- `/admin-login`, `/admin-logout`, `/admin-set-creds`, `/ban` commands
- `LNAPIAdminClient` in `automation/admin_api.py`
- `utils/encryption.py` for credential encryption

### Fixed
- Various bug fixes and stability improvements

## v2.0.0 (2026-05-09)

### Added
- Unified command structure
- `/settings` with persistent per-guild configuration
- `/do` with multi-task support
- `/logs` for user/homework/bot logs
- `/reload` for hot-reloading cogs
- Autocomplete with 20s TTL cache
- Token refresh with proper locking
- Atomic config writes (temp+rename)
- Error handler with CommandInvokeError unwrapping

### Performance
- Shared aiohttp session with connection pooling
- asyncio.Semaphore-based concurrent task execution (1-8)
- Auto-retry with configurable attempts and backoff
- Precompiled regex for gameLink parsing

### Settings
- Speed (sec/task)
- Min/Max accuracy (%)
- Concurrency (parallel tasks)
- Retry attempts
- Stealth toggle
- Auto-retry toggle
- Reset to defaults
