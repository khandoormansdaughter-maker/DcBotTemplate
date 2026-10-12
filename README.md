# DcBotTemplate

A minimal Python Discord bot template designed to run on GitHub Actions.

## Features

- A simple `/ping` slash command that responds with the bot's latency.
- Python 3.12 and `discord.py`.
- Manual starts with **Actions → Run Discord bot → Run workflow**.
- Scheduled runner windows every six hours (UTC).

## Setup

1. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Add the bot to your server with the `bot` and `applications.commands` scopes.
3. In this GitHub repository, open **Settings → Secrets and variables → Actions**.
4. Create a repository secret named `DISCORD_TOKEN` containing the bot token. Do not commit the token to source control.
5. Open the **Actions** tab, enable workflows if prompted, then run **Run Discord bot** manually.
6. Invite the bot to a server and try `/ping`. Global slash-command registration can take a little while to propagate.

## Run locally

Install Python 3.12+, then:

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Set `DISCORD_TOKEN` in your environment and run:

```bash
python bot.py
```

## GitHub Actions runtime notes

The workflow starts at 00:00, 06:00, 12:00, and 18:00 UTC and ends each bot process after 5 hours 45 minutes to stay within the runner limit. This leaves a nominal 15-minute gap between scheduled windows, and GitHub can delay scheduled runs. The concurrency setting prevents scheduled runs from intentionally cancelling one another, but queued runs can increase downtime.

**This is best-effort hosting, not guaranteed 24/7 uptime.** GitHub Actions is not a dedicated bot-hosting service; for dependable continuous availability, use a host designed for long-running processes.

## Project layout

- `bot.py` — Discord client and `/ping` command
- `requirements.txt` — Python dependencies
- `.github/workflows/bot.yml` — scheduled and manual workflow
