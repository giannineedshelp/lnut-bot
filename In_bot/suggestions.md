
---

## `SUGGESTIONS.md`

```markdown
# Suggestions — LanguageNut Bot

## 🔧 Technical Improvements

### 1. Use One API Client, Not Two
**Current:** `api_direct.py` has TWO clients — `LanguagenutClient` (sync, curl_cffi) and `LNApiClient` (async, aiohttp). The new `commands.py` uses `LanguagenutClient` but the old one used `LNApiClient`.

**Suggestion:** Pick ONE and delete the other. The async `LNApiClient` is more reliable since it reuses the bot's `aiohttp.ClientSession`. Refactor `commands.py` to use `LNApiClient` instead.

### 2. Fix GitHub Truncation — Split Into Smaller Files
**Current:** `api_direct.py`, `commands.py`, and other files are too large — GitHub cuts them off.

**Suggestion:** Split `commands.py` into:
- `cogs/command_centre.py` — hub, login, logout, status
- `cogs/farm.py` — farm execution
- `cogs/health.py` — account health check
- `cogs/help.py` — help menu

### 3. Add Proper Logging for API Calls
**Current:** API calls are logged but sensitive params (password, token) are only partially sanitized.

**Suggestion:** Add a `_sanitize_params()` wrapper that redacts all sensitive fields before logging.

### 4. Cache Sessions in a Database
**Current:** Sessions are stored in an in-memory dict (`sessions: Dict[int, Dict[str, Any]]`). Lost on bot restart.

**Suggestion:** Use SQLite or JSON file storage so logins persist across restarts.

---

## 🎮 User Experience

### 1. Make Hub Persistent (Not Ephemeral)
**Current:** The `/hub` message is ephemeral — it disappears on restart or after timeout.

**Suggestion:** Add a "📌 Pin this panel" toggle that makes the hub persistent in a dedicated channel.

### 2. Farm Progress in DMs
**Current:** Farm progress is shown in the ephemeral message.

**Suggestion:** Send DM updates every 5 tasks with a live progress bar and estimated time remaining.

### 3. Add "Stop Farming" Button
**Current:** Once farming starts, there's no way to cancel.

**Suggestion:** Add a "🛑 Stop" button that sets a cancellation flag.

### 4. Show XP/hour Rate
**Current:** Farm results show total XP but not rate.

**Suggestion:** Calculate and display `XP/hour` and estimated time to next level/goal.

---

## 🛡️ Stealth & Anti-Detection

### 1. Randomized Task Order
**Current:** Tasks are farmed in order.

**Suggestion:** Shuffle task order within a homework to look more natural.

### 2. Random Time Gaps Between Sessions
**Current:** Stealth handles delays within a session.

**Suggestion:** Add a random gap (5-30 minutes) between consecutive farming sessions to mimic real student behaviour.

### 3. Session Length Capping
**Current:** Can farm continuously until XP target is reached.

**Suggestion:** Cap sessions at 30-45 minutes max, then require a break, just like a real student would take.

---

## 📊 Monitoring

### 1. Ban Detection Webhook
**Suggestion:** Send a Discord webhook (or DM the owner) when any account is detected as banned.

### 2. Daily Summary Report
**Suggestion:** Post a daily embed showing: accounts checked, XP earned, bans detected, tasks completed.

### 3. Account Health History
**Suggestion:** Log daily health check results to track if accounts are degrading over time (accuracy drops, etc).

---

## 🏗️ Architecture

### 1. Move to Discord.py 2.4+ Features
**Suggestion:** Use new features like `app_commands.ContextMenu`, modals with dropdowns, and persistent views (timeout=None for permanent buttons).

### 2. Add Command Cooldowns
**Suggestion:** `/farm` should have a per-user cooldown (e.g. 5 seconds) to prevent spam.

### 3. Support for Multiple Languages Simultaneously
**Suggestion:** Let users create "farm queues" for multiple languages that run sequentially.
