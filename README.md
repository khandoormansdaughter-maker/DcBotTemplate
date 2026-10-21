# DcBotTemplate — Translator branch

This branch adds Google Translate-powered translation using an **official Discord bot application**. It does not automate a personal Discord user account: Discord prohibits self-bots. To automatically translate messages in a server channel, the bot must be invited there and have permission to read and send messages.

## Translation features

- `/translate text:` translates supplied text to your personal target language.
- Right-click a message and choose **Apps → Translate message** to translate that message and show its author.
- `/language language:` sets your preferred target language; defaults to English (`en`).
- `/channel channel: language:` enables automatic translation in a server text channel; destination defaults to English.
- `/channel_off channel:` disables automatic translation for a channel.
- Settings are stored in `translator_settings.json` on the running host.

## Setup

1. Create an application and bot user in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Invite the bot with the `bot` and `applications.commands` scopes. Grant View Channel, Read Message History, and Send Messages permissions where translation is needed.
3. Add repository secret `DISCORD_TOKEN` with the bot token.
4. In **Bot → Privileged Gateway Intents**, enable **Message Content Intent** for automatic channel translation.
5. The existing workflow uses `BOT_WORKFLOW_TOKEN` for runner handoff. Start it from **Actions → Run Discord bot → Run workflow**.
6. For local development, install dependencies using `python -m pip install -r requirements.txt`, set `DISCORD_TOKEN`, and run `python bot.py`.

## Important limitations

- `googletrans` accesses an unofficial Google Translate web interface; it is not Google's paid Cloud Translation API and may be rate-limited or change unexpectedly. For production use, replace it with the official Google Cloud Translation client and configure credentials.
- Automatic translation only runs in channels configured with `/channel`. It cannot monitor arbitrary messages from a personal Discord account or messages the bot cannot access.
- `translator_settings.json` is runtime-local state. GitHub-hosted runners are ephemeral, so settings can be lost when the workflow hands off to a new runner. Use persistent storage or a database if settings must survive restarts.
- Never commit bot tokens or translation credentials.

## Original runner workflow

The existing GitHub Actions workflow retains its readiness-checked runner handoff and scheduled recovery behavior. This is best-effort hosting, not guaranteed 24/7 uptime.
