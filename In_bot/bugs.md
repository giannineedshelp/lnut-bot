# Known Bugs — LanguageNut Bot

## ~~🐛 Login Broken (Critical)~~ ✅ FIXED v2.1.1
**Status:** Fixed  
**Fix:** The `LanguagenutClient.login()` now uses `"pass"` parameter (not `"password"`) and looks for `"newToken"` in the response. Matches the working async `LNApiClient` behavior.

## ~~🐛 Account Health Shows "Not Logged In" for Banned Accounts~~ ✅ FIXED v2.1.1
**Status:** Fixed  
**Fix:** Health check now handles 401/403 responses properly. If login succeeds but profile returns ban data, it shows ban status with unban timer instead of "not logged in".

## ~~🐛 Voice Channel Feature Doesn't Work~~ ✅ FIXED v2.1.1
**Status:** Fixed  
**Fix:** Simplified to just channel name edits (no voice connection needed). Cleaner status names: 🟢 Online, 🌾 Farming, 🟡 Idle, 🔴 Offline.

## ~~🐛 Rate Limiting on Status Channel (429 Errors)~~ ✅ FIXED v2.1.1
**Status:** Fixed  
**Fix:** Added exponential backoff with jitter. Reduced update frequency. Removed `user_limit` edits (which caused extra API calls).

## ~~🐛 Old Cached Commands Cause CommandNotFound~~ ✅ FIXED v2.1.1
**Status:** Fixed  
**Fix:** `setup_hook` now calls `tree.clear_commands(guild=guild)` for all guilds before syncing. Admin panel sync button also clears old commands first.
