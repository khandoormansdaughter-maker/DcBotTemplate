# DcBotTemplate

A Python Discord bot template with optional Gemini AI chat.

## Features

- /ping checks latency.
- /prompt sets a per-user, per-channel character/persona instruction for Gemini.
- /ask sends a question using your current character prompt.
- Mention the bot with a question or reply to one of its messages to chat in character.
- Mention the bot with supported server-management requests to create text/voice/category/forum channels, create forum posts, create roles, move channels, restrict channel visibility to a role, route replies to a channel, kick/ban mentioned members, and assign/remove roles. Every change asks for confirmation and checks the requester's Discord permissions; Discord bot permissions and role hierarchy still apply.

Example requests (mention the bot first):

- `create a forum called suggestions`
- `create a post in <#FORUM_CHANNEL_ID> titled "Feature idea": Let people vote on this idea`
- `create a text channel called bot-chat`
- `create a role called Helpers`
- `move <#CHANNEL_ID> into category Community`
- `restrict <#CHANNEL_ID> to <@&ROLE_ID>`
- `send your replies in <#CHANNEL_ID>`
- `kick <@MEMBER_ID>` or `ban <@MEMBER_ID>`
- `assign <@MEMBER_ID> role <@&ROLE_ID>` or `remove <@&ROLE_ID> from <@MEMBER_ID>`

Use actual Discord mentions for existing channels, roles, and members. The bot asks for confirmation before it changes anything. Forum-post creation is supported inside an existing forum channel.
- Short per-channel, per-user conversation history and character prompts are kept in memory; both reset on restart.
- GitHub Actions startup and best-effort runner handoff/recovery.

## Setup

1. Create a Discord application and bot in the Discord Developer Portal: https://discord.com/developers/applications
2. Invite it with the bot and applications.commands scopes.
3. In Developer Portal → Bot → Privileged Gateway Intents, enable **Message Content Intent**. Mention/reply chat requires this.
4. When inviting the bot, grant only the permissions it needs for the features you plan to use. Server management needs **Manage Channels**; role management needs **Manage Roles**; kicking/banning needs **Kick Members** and/or **Ban Members**. Discord role hierarchy still limits which members and roles the bot can manage. Avoid granting Administrator unless you truly need it.
5. In repository Settings → Secrets and variables → Actions, add these repository secrets:
   - DISCORD_TOKEN: Discord bot token.
   - GEMINI_API_KEY: Gemini API key from https://aistudio.google.com/apikey
   - BOT_WORKFLOW_TOKEN: fine-grained PAT limited to this repository with Actions: Read and write permission, for workflow handoff/recovery.
6. Never commit or share tokens/API keys. Store them only as secrets or environment variables.
7. Open Actions → Run Discord bot → Run workflow. Try /ping, use /prompt to set a character (for example, “You are a cheerful space explorer who explains things simply”), then use /ask or mention/reply to chat.

Gemini is optional. Without GEMINI_API_KEY, the bot starts and /ping works, but AI requests explain how to configure the key. The key is read at startup, so restart the workflow after adding/changing it.

## Run locally

Install Python 3.12+, then run:

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    python bot.py

On Windows PowerShell, activate with .venv\\Scripts\\Activate.ps1. Set DISCORD_TOKEN and optionally GEMINI_API_KEY in your environment first. Optional Gemini settings: GEMINI_MODEL (default: gemini-3.8-flash), GEMINI_TIMEOUT_MS (default: 15000), and GEMINI_MAX_OUTPUT_TOKENS (default: 700). Lower output-token limits can reduce response time but also shorten answers. Gemini calls use a 15-second request timeout by default and one quick retry for temporary server errors/timeouts, rather than the SDK's long retry backoff.

## Limitations

The runner handoff is best-effort, not guaranteed 24/7 hosting. GitHub may delay workflows or runners may fail. Conversation history is not persisted across restarts. Prompts and replies are sent to Google's Gemini API. Server reply routing and conversation/persona state are in memory and reset on restart. Management requests currently use a limited set of natural-language patterns; kick/ban/role assignment require explicit member or role mentions. A dedicated application host is recommended for dependable uptime.

## Project layout

- bot.py — Discord client, Gemini chat, /ping, /prompt, and /ask
- requirements.txt — Python dependencies
- .github/workflows/bot.yml — runner startup, handoff, and recovery
