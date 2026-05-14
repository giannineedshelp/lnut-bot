# Known Bugs — LanguageNut Bot

## 🐛 Login Broken (Critical)
**Status:** Open  
**Priority:** HIGH  
**Description:** The `LanguagenutClient.login()` method in `api_direct.py` fails to authenticate. Users get "Login Failed" with no clear error.

**Root Cause (suspected):**
- The login method is using the wrong parameter name — LanguageNut expects `"pass"` not `"password"`
- OR the code is using `"newToken"` but looking for `"token"` in the response
- OR the sync client (`curl_cffi`/`requests`) doesn't properly handle the auth endpoint whereas the async client (`aiohttp`) does

**Fix:** 
1. Read the full login method from the file (GitHub truncates it)
2. Compare with the working async `LNApiClient.login()` which uses `{"username": ..., "pass": ...}` and looks for `newToken`
3. Either fix the sync client or switch to the async client

**Workaround:** Use the `LNApiClient` (async) instead of `LanguagenutClient` (sync)

---

## 🐛 Account Health Shows "Not Logged In" for Banned Accounts
**Status:** Open  
**Priority:** HIGH  
**Description:** When an account is banned/suspended, the API returns 401/403. The bot interprets this as "not logged in" instead of "banned".

**Expected:** Show "Account Banned — Unban in 2d 4h" or similar.

**Fix:** The `_check_account_banned()` function exists but login fails before we get there. Need to handle the case where token exists but API returns 401/403.

---

## 🐛 Voice Channel Feature Doesn't Work
**Status:** Open  
**Priority:** MEDIUM  
**Description:** The voice channel feature (if implemented) doesn't connect or play audio.

**Possible Causes:**
- FFmpeg not installed on the machine running the bot
- Discord voice intents not enabled
- Missing `discord.py[voice]` dependencies
- Bot doesn't have voice channel permissions in the server

**Fix:** Check environment for FFmpeg, verify intents, test with a simple `join`/`play` command.

---

## 🐛 Rate Limiting on Status Channel (429 Errors)
**Status:** Open  
**Priority:** MEDIUM  
**Description:** The bot gets `HTTP 429 Too Many Requests` when updating the status channel via PATCH.

**Logs:** `429 on PATCH status channel — retrying in 102s, then 582s`

**Fix:** Add exponential backoff with jitter for status channel updates. Consider reducing update frequency.

---

## 🐛 Old Cached Commands Cause CommandNotFound
**Status:** Open  
**Priority:** HIGH  
**Description:** Discord still knows about `/hub`, `/admin-students`, `/account-health` from a previous version. Users get `CommandNotFound` errors.

**Fix:** 
```python
self.tree.clear_commands(guild=guild)
self.tree.copy_global_to(guild=guild)
await self.tree.sync(guild=guild)
