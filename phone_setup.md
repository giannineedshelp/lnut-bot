# Lnut-Bot on Android (Termux)

## Quick Start

1. **Install Termux** from F-Droid (avoid Play Store version)
2. Open Termux and run:
   ```
   pkg update && pkg upgrade
   pkg install python git
   ```
3. Clone the repo and run:
   ```
   git clone https://github.com/giannineedshelp/lnut-bot.git
   cd lnut-bot
   cp .env.example .env
   nano .env
   ```
   - `DISCORD_TOKEN=your_discord_bot_token`
   - `GUILD_ID=your_discord_server_id` (optional)
4. Start the bot:
   ```
   bash run.sh
   ```
   This auto-installs deps and pulls updates.

## One-Click Update (from phone)
```
python update.py
```
Then start with `bash run.sh`.

## Running 24/7
- Install Termux:Boot from F-Droid
- `termux-setup-storage`
- Create `~/.termux/boot/start-bot.sh` with:
  ```bash
  cd ~/lnut-bot
  python update.py
  bash run.sh
  ```

## Access Remotely
- Bot connects outbound to Discord — no port forwarding needed
- Control via slash commands: `/login`, `/homework`, `/do`
- Logs in `logs/bot.log`
- For SSH: `pkg install openssh`, `sshd`, connect from PC

**Security**: Never share .env. Use strong Discord bot token with minimal perms.

