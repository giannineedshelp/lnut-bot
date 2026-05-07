# lnut-bot

LanguageNut Discord automator bot.

## Features
- Encrypted credential storage (Fernet)
- Interactive `/settings` panel with persistent per-guild values
- Concurrent task execution with auto-retry
- Paginated `/homework` list (fixes 25-field embed crash)
- Comma-separated multi-task `/do`
- Cached autocomplete for speed
- Owner-only admin suite (`/restart`, `/update`, `/reload`, etc.)

## Setup
1. `cd In_bot`
2. Copy `.env.example` to `.env` and fill in values
3. `pip install -r requirements.txt`
4. `python main.py`

## Project layout
See `In_bot/structure.txt` for the current file tree.
All bot code is inside `In_bot/`. The commands have been merged into a single
`commands/commands.py` module.
