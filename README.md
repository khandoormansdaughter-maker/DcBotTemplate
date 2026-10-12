# DcBotTemplate

A Python Discord bot template with optional Gemini AI chat.

## Features

- /ping checks latency.
- /prompt lets users ask Gemini questions.
- Mention the bot with a question or reply to one of its messages to chat.
- Short per-channel, per-user conversation history (in memory; resets on restart).
- GitHub Actions startup and best-effort runner handoff/recovery.

## Setup

1. Create a Discord application and bot in the Discord Developer Portal: https://discord.com/developers/applications
2. Invite it with the bot and applications.commands scopes.
3. In Developer Portal → Bot → Privileged Gateway Intents, enable **Message Content Intent**. Mention/reply chat requires this.
4. In repository Settings → Secrets and variables → Actions, add these repository secrets:
   - DISCORD_TOKEN: Discord bot token.
   - GEMINI_API_KEY: Gemini API key from https://aistudio.google.com/apikey
   - BOT_WORKFLOW_TOKEN: fine-grained PAT limited to this repository with Actions: Read and write permission, for workflow handoff/recovery.
5. Never commit or share tokens/API keys. Store them only as secrets or environment variables.
6. Open Actions → Run Discord bot → Run workflow. Try /ping, /prompt, or mention the bot in a channel.

Gemini is optional. Without GEMINI_API_KEY, the bot starts and /ping works, but AI requests explain how to configure the key. The key is read at startup, so restart the workflow after adding/changing it.

## Run locally

Install Python 3.12+, then run:

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    python bot.py

On Windows PowerShell, activate with .venv\\Scripts\\Activate.ps1. Set DISCORD_TOKEN and optionally GEMINI_API_KEY in your environment first. GEMINI_MODEL is optional (default: gemini-2.5-flash).

## Limitations

The runner handoff is best-effort, not guaranteed 24/7 hosting. GitHub may delay workflows or runners may fail. Conversation history is not persisted across restarts. Prompts and replies are sent to Google's Gemini API. A dedicated application host is recommended for dependable uptime.

## Project layout

- bot.py — Discord client, Gemini chat, /ping, and /prompt
- requirements.txt — Python dependencies
- .github/workflows/bot.yml — runner startup, handoff, and recovery
