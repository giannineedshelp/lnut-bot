# LanguageNut Discord Bot — User Guide

## What is this?

A Discord bot that automates LanguageNut homework assignments. It submits realistic per-vocab timing and accuracy to avoid detection.

## Setup

### Requirements
- Python 3.10+
- discord.py 2.4.0, aiohttp, python-dotenv, cryptography

### Quick Start
1. `pip install -r requirements.txt`
2. Create `.env` in the `In_bot` folder (see example below)
3. `python main.py`

### .env File
```
DISCORD_TOKEN=your_bot_token_here
ENCRYPTION_KEY=your_32byte_base64_key_here
GUILD_ID=your_discord_server_id
OWNER_ID=your_discord_user_id
HEADLESS=true
LOG_LEVEL=INFO
```

> **Note:** The bot auto-detects `.env` in both `In_bot/` and the parent directory.

## Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/login` | Log in to LanguageNut with your username/password |
| `/logout` | Log out and clear stored credentials |
| `/homework` | Show all assignments with progress |
| `/do` | Interactive task selector — pick tasks to auto-complete |
| `/quick-do` | Quick-complete by homework:index (e.g. `123:0`) with autocomplete |
| `/settings` | Customize timing, accuracy, concurrency, and retry settings |
| `/status` | Show bot stats (servers, latency, login status) |
| `/tutorial` | Show this guide in Discord |

### Admin Commands (owner only)

| Command | Description |
|---------|-------------|
| `/sync` | Sync slash commands (after code changes) |
| `/reload` | Reload a cog without restart |
| `/clear` | Delete recent messages (1-100) |
| `/logs` | Show last 20 log lines |
| `/update` | Git pull + auto-restart |
| `/restart` | Restart the bot |
| `/shutdown` | Stop the bot |
| `/eval` | Execute Python code (for debugging) |
| `/online` | @everyone announce bot online |
| `/offline` | @everyone announce bot offline |

## Per-Question Timing (Customizable)

Each vocabulary item in a task gets a **random completion time** in your chosen range.

**Default:** `5–8 seconds per question`

Example with 20 vocab items:
- Each item: random 5–8s → average 6.5s
- Total timestamp: ~130 seconds (cumulative sum + small jitter)

### How to Configure

Run `/settings` and use the buttons:
- **Time Per-Q Min** — Set the minimum seconds per question (1–300s)
- **Time Per-Q Max** — Set the maximum seconds per question (1–300s)

If Min > Max, the bot auto-swaps them.

## Settings Panel

`/settings` opens an interactive panel with these options:

| Button | What it does |
|--------|-------------|
| Time Per-Q Min | Minimum seconds per question (1–300) |
| Time Per-Q Max | Maximum seconds per question (1–300) |
| Min Accuracy | Minimum accuracy % (0–100) |
| Max Accuracy | Maximum accuracy % (0–100) |
| Concurrency | Number of parallel tasks |
| Retry Attempts | Max retries per failed task |
| Stealth Toggle | On/off for accuracy/stealth features |
| Auto Retry | On/off for automatic retry on failure |
| Reset | Reset all settings to defaults |

Accuracy range works like timing: each task picks a random accuracy target within [Min%, Max%]. Only that percentage of vocabs are marked "correct" — mimicking human performance.

## /do vs /quick-do

**`/do`** — Interactive homework browser with dropdown selectors. Best for:
- First-time use
- Browsing available assignments
- Selecting specific tasks visually

**`/quick-do`** — Fast parameter-based completion using `hwId:idx` syntax. Best for:
- Power users who know the homework IDs
- Batching multiple tasks: `123:0,456:2,789:4`
- Scripting / repeated runs

Autocomplete shows available incomplete tasks as you type.

## How Timing Works (Technical)

1. `StealthManager.compute_timestamp(num_questions)` is called with the vocabulary count
2. For each question, a random value in [min_sec, max_sec] is generated
3. All values are summed
4. A small jitter (`random.uniform(-0.5, 1.5)`) is added
5. The total is converted to milliseconds and sent as `timeStamp`

This creates a realistic cumulative completion time that varies per submission.

## Troubleshooting

**"Application didn't respond"**
All commands use `interaction.response.defer()` to get the 15-minute thinking window. If you still see this, the LanguageNut API might be timing out. Try reducing `concurrency` in `/settings`.

**"Not logged in"**
Use `/login` with your LanguageNut credentials (username/password from languagenut.com, not Discord).

**Commands not appearing**
Run `/sync` (owner only) to refresh the command list. Discord can take up to 1 hour for global commands, or instant for guild-scoped.

**Bot crashing on startup**
Check `.env` exists with valid `DISCORD_TOKEN`. Check `GUILD_ID` is a valid Discord server ID (enable Developer Mode in Discord → right-click server → Copy ID).

**Autocomplete not working**
Autocomplete uses a 30-second cache. If tasks have changed recently, wait 30s or open `/do` to force-refresh the cache.

## File Structure

```
In_bot/
├── main.py                 # Entry point
├── config.py               # Settings & account storage
├── requirements.txt        # Python dependencies
├── tutorial.md             # This file
├── run.bat                 # Windows launcher
├── .env                    # Environment variables (token, keys)
├── config.json             # Per-guild settings & accounts (auto-created)
├── logs/bot.log            # Log file (auto-created)
├── automation/
│   ├── api_direct.py       # LanguageNut HTTP client
│   ├── discover.py         # Homework discovery
│   └── stealth.py          # Timing & accuracy engine
├── commands/
│   └── commands.py         # All slash commands
└── utils/
    ├── encryption.py       # Fernet credential encryption
    ├── helper.py           # Utility functions
    └── logger.py           # Logging setup
```
