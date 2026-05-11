# LanguageNut Bot — Server Usage Guide

## What is this?

A Discord bot that automates LanguageNut homework on **this server**. It completes assignments with realistic timing and accuracy so you don't have to do them manually.

## Quick Start

1. **`/login`** — Enter your LanguageNut username and password (stored encrypted, only you can use)
2. **`/homework`** — View all pending assignments
3. **`/do`** — Select tasks to complete, or use `/quick-do` for fast task selection

That's it. The bot handles everything else.

## Available Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/login` | Log in to LanguageNut with your username/password |
| `/logout` | Remove stored credentials |
| `/homework` | Show all assignments with progress bars |
| `/do` | Interactive task selector — browse and pick tasks |
| `/quick-do` | Quick-complete by homework:index (e.g. `123:0`) |
| `/settings` | Customize timing, accuracy, concurrency, retries |
| `/status` | Show bot stats and your login status |
| `/leaderboard` | View class, school, or world rankings |
| `/tutorial` | Show this guide |

### Admin Commands (owner only)

| Command | Description |
|---------|-------------|
| `/sync` | Refresh slash commands after code changes |
| `/reload` | Reload bot module without restart |
| `/logs` | View user usage, homework history, or bot logs |
| `/update` | Git pull + auto-restart |
| `/restart` | Restart the bot |
| `/shutdown` | Stop the bot |
| `/clear` | Delete recent messages (1-100) |

## Doing Homework

### With `/do` (recommended for first use)

1. Run `/do` — an interactive menu shows your assignments
2. Select a homework assignment from the dropdown
3. Pick specific tasks (or \"Do ALL\")
4. The bot processes them and reports results

### With `/quick-do` (for power users)

Format: `homeworkId:taskIndex` (comma-separated for batch)

**Examples:**
- `/quick-do 123:0` — Complete task #0 in homework #123
- `/quick-do 123:0,456:2,789:4` — Complete 3 tasks at once

Autocomplete shows available tasks as you type.

## Customizing Settings

Run `/settings` to open the control panel:

| Setting | What it does |
|---------|-------------|
| Time Per-Q (Min/Max) | How many seconds per vocabulary item (5-8s default) |
| Accuracy (Min/Max) | What % of answers are marked correct |
| Concurrency | How many tasks run in parallel (1-8) |
| Retry Attempts | How many times to retry on failure |
| Stealth Toggle | Enable/disable realistic behavior |

Accuracy works like timing: each task picks a random accuracy within [Min%, Max%]. The remaining vocabs are marked \"wrong\" — mimicking real human performance.

## Leaderboard Types

| Command | What it shows |
|---------|---------------|
| `/leaderboard class` | Students in your class, ranked by score |
| `/leaderboard school` | All students in your school |
| `/leaderboard global` | Worldwide school competition rankings |

## Tips

- **Mobile users:** The bot works on mobile Discord. Select menus and buttons are fully compatible.
- **First use:** `/login` then `/homework` then `/do` — three commands and you're set.
- **Check progress:** Run `/homework` anytime to see updated progress bars.
- **Concurrency:** Increase concurrency in `/settings` for faster batch processing (higher = more API load).
- **Wait for results:** Heavy batches may take a few minutes. The bot posts results when done.

## Troubleshooting

**"Not logged in"** — Use `/login` with your LanguageNut credentials.

**"Homework not found"** — Run `/homework` first to refresh the cache, then `/do`.

**Commands not appearing** — An admin needs to run `/sync`.

**Bot not responding** — Commands defer automatically for a 15-minute window. If you still get timeout, the LanguageNut API may be slow. Try reducing concurrency in `/settings`.

