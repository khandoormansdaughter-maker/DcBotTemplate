# SllBot

SllBot is a lightweight Discord server-action bot. It extracts supported intents from addressed messages, checks permissions, and calls the Discord API. It uses a rule-based parser, not speech recognition or an LLM.

## Supported requests

Address the bot in a server channel by starting with “hey doll”, “doll,”, or mentioning the bot.

- “Hey doll, create a channel named hello thanks” — creates a text channel.
- “Hey doll, make a forum called ideas” — creates a forum channel.
- “Hey doll, start a thread named planning” — starts a thread in the current text channel using the request as its starter message.
- “Hey doll, create a role named Event Team” — creates a role without elevated permissions.

Channel and forum names are normalized to lowercase and hyphens. Duplicate resources are checked before creation.

## Permissions

- Text channels and forums: both requester and bot need Manage Channels.
- Roles: both requester and bot need Manage Roles.
- Threads: both requester and bot need Create Public Threads.
- Discord's own permission checks and role hierarchy still apply.

## Setup

1. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Invite it with the bot and applications.commands scopes.
3. Enable Developer Portal → Bot → Privileged Gateway Intents → Message Content Intent.
4. Add DISCORD_TOKEN under GitHub → Settings → Secrets and variables → Actions. Never commit or share the token.
5. Grant only the permissions needed for the actions you want to enable.
6. Configure BOT_WORKFLOW_TOKEN for the existing GitHub Actions runner handoff as described in the repository workflow/setup.
7. Run Actions → Run Discord bot → Run workflow, or run locally.

## Run locally

Install Python 3.12+, then run:

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    python bot.py

Set DISCORD_TOKEN before starting. BOT_READY_FILE is optional and used by the GitHub Actions workflow.

## Limitations

This is a small rule-based parser. Unknown requests are not executed. Creating a role does not grant permissions or assign the role to anyone. Expand the allowlist deliberately and keep permission checks in every handler.

## Project layout

- bot.py — Discord client, intent parser, resource actions, and /ping
- requirements.txt — Python dependencies
- .github/workflows/bot.yml — runner startup, handoff, and recovery check
