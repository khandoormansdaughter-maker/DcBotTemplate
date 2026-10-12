# SllBot

A lightweight Discord server-action bot built from DcBotTemplate. It reads addressed messages, extracts a supported intent, checks Discord permissions, and performs the action. It does not use speech recognition, text-to-speech, or an LLM.

## Current natural-language action

In a server channel, write something like:

> Hey doll, can you create a channel named "hello" thanks.

SllBot recognizes create/make/add channel phrasing and creates a text channel named hello. It normalizes spaces to hyphens and lowercase. It ignores bot messages and DMs, avoids creating a duplicate channel, and reports permission/API errors rather than claiming success.

This is a deliberately small, rule-based intent parser. Unknown requests are not executed. Add new explicit intent patterns and handlers as more actions are implemented.

## Setup

1. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Invite the bot with the bot and applications.commands scopes. Grant **Manage Channels** for channel creation.
3. In **Developer Portal → Bot → Privileged Gateway Intents**, enable **Message Content Intent**. The bot needs this to read ordinary messages.
4. In GitHub, open **Settings → Secrets and variables → Actions** and add DISCORD_TOKEN with your bot token. Never commit or share the token.
5. For the existing GitHub Actions runner handoff, configure BOT_WORKFLOW_TOKEN as described in the workflow/repository setup.
6. Run **Actions → Run Discord bot → Run workflow**. You can also run locally.

## Run locally

Install Python 3.12+, then:

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python bot.py
```

Set DISCORD_TOKEN in your environment before starting the bot. BOT_READY_FILE is optional and used by the GitHub Actions workflow.

## Safety and limitations

- The bot only processes messages in servers when they start with hey doll / doll, or mention the bot.
- Only explicitly implemented intents run; it does not interpret arbitrary text as executable instructions.
- Discord's role hierarchy and server permissions still apply. The bot checks its Manage Channels permission and handles Discord API denials.
- Creating or changing server resources should remain limited to allowlisted actions with validated arguments. Require confirmation before adding destructive actions such as deleting channels or roles.
- This is not an LLM. For more flexible language understanding, a later version could add an optional model-based intent classifier while keeping the same strict action allowlist and permission checks.

## Project layout

- bot.py — Discord client, message intent parsing, channel creation, and /ping
- requirements.txt — Python dependencies
- .github/workflows/bot.yml — runner startup, handoff, and recovery check
