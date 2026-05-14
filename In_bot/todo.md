
---

## `TODO.md`

```markdown
# TODO — LanguageNut Bot

## Current Sprint

### 🐛 Login Not Working
- [ ] **Fix `LanguagenutClient.login()`** — the sync client in `api_direct.py` is truncated on GitHub
- [ ] **Verify param names**: LN expects `"pass"` not `"password"` in `loginController/attemptLogin`
- [ ] **Check login response**: should return `newToken` (not `token`)
- [ ] **Fallback**: If sync client fails, switch commands.py to use async `LNApiClient` instead

### 🐛 Account Health Shows "Not Logged In" For Banned Accounts
- [ ] **Fix health check**: When account is banned, login returns a 401/403 — we should detect this and show "Banned" instead of "Not Logged In"
- [ ] **Add ban detection**: Check for keywords like "banned", "suspended" in error responses
- [ ] **Unban timer**: Parse `unbanAt`, `suspendedUntil` fields if LN returns them

### 🐛 Voice Channel Feature Doesn't Work
- [ ] Investigate what the voice channel feature is supposed to do
- [ ] Check Discord voice permissions for the bot
- [ ] Ensure FFmpeg is installed in the environment
- [ ] Test voice connection and playback

### 🌾 Farm XP — Language/Topic/XP Selection
- [ ] **LanguageSelect** — dropdown for 25+ languages (DONE in new code)
- [ ] **TopicSelect** — show homework names for chosen language (DONE)
- [ ] **XP Target** — quick select + custom modal (DONE)
- [ ] **Filter tasks**: Only farm incomplete tasks matching language & topic
- [ ] **Stop at target**: Exit early once XP target is reached

### 🔄 Syncing Issues
- [ ] Old cached commands `/hub`, `/admin-students`, `/account-health` are registered but code is missing
- [ ] Need `tree.clear_commands(guild=guild)` before re-sync
- [ ] Confirm xp_commands cog is loaded alongside commands cog

### 📄 Documentation
- [ ] Create `lNut_APIs.md` (DONE)
- [ ] Create `TODO.md` (DONE)
- [ ] Create `BUGS.md` (DONE)
- [ ] Create `SUGGESTIONS.md` (DONE)

## Medium Priority
- [ ] **Rate limiting**: Bot gets 429 errors when PATCHing status channel — add retry logic
- [ ] **Stealth settings**: Allow users to adjust min/max accuracy and speed from `/settings`
- [ ] **Multi-account**: Support saving and switching between multiple LN accounts
- [ ] **Live progress bar**: DM the user with farm progress updates

## Future
- [ ] **Free activities mode**: Farm from independent learning resources (not just homework)
- [ ] **Web dashboard**: Flask-based UI for monitoring accounts
- [ ] **Push notifications**: Get pinged when a ban is detected
- [ ] **Analytics**: Track XP/hour, ban rates, success rates per account
