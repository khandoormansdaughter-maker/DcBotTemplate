# DcBotTemplate — Translator branch

Translator is configured as a **user-installed Discord app**. You add it to your own Discord account with **Add to my apps** instead of adding its bot user to every server. Its commands can be used in servers you can access, even when Translator is not a member of those servers.

This is an official Discord application, not a self-bot. It only processes text that Discord supplies when you invoke a command; it does not passively read messages from your account.

## Translation features

- `/translate text:` translates text you provide into your personal target language.
- On a message, open its context menu and choose **Apps → Translate message** to translate that specific message and show who wrote it. The result is visible only to you.
- `/language language:` sets your preferred target language; defaults to English (`en`).
- `/ping` checks whether the app is responding.
- Language preferences are stored in `translator_settings.json` on the running host.

## What it can and cannot do

A user-installed app can be used in servers where it has not been installed as a server bot, but Discord does **not** give it a live feed of all messages in those servers. Therefore:

- You can manually translate a message by selecting **Apps → Translate message**.
- It cannot automatically translate every new message in a channel where it is not installed as a server bot.
- It does not read messages through your personal account or use a self-bot.

Discord documents user-installed apps and their limitations here: [User-installable apps](https://discord.com/developers/docs/tutorials/developing-a-user-installable-app).

## Discord Developer Portal setup

1. Open your app in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Go to **Installation** and enable **User Install**. You can turn off **Guild Install** if you want this app to be account-installed only.
3. Under **Default Install Settings → User Install**, select the `applications.commands` scope. A user install does not need the `bot` scope or server permissions.
4. Use the app's install link and choose **Add to my apps**.
5. Add the repository secret `DISCORD_TOKEN` with the application's bot token so the existing runner can connect and sync commands.
6. The existing workflow uses `BOT_WORKFLOW_TOKEN` for runner handoff. Start it from **Actions → Run Discord bot → Run workflow**.
7. For local development, install dependencies using `python -m pip install -r requirements.txt`, set `DISCORD_TOKEN`, and run `python bot.py`.

Message Content Intent is not required for the interaction-only version.

## Translation provider and persistence notes

- `googletrans` accesses an unofficial Google Translate web interface; it is not Google's paid Cloud Translation API and may be rate-limited or change unexpectedly. For production use, replace it with the official Google Cloud Translation client and configure credentials.
- `translator_settings.json` is runtime-local state. GitHub-hosted runners are ephemeral, so preferences can be lost when the workflow hands off to a new runner. Use persistent storage or a database if settings must survive restarts.
- Never commit bot tokens or translation credentials.

## Original runner workflow

The existing GitHub Actions workflow retains its readiness-checked runner handoff and scheduled recovery behavior. This is best-effort hosting, not guaranteed 24/7 uptime.
