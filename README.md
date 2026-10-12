# DcBotTemplate

A minimal Python Discord bot template designed to demonstrate a readiness-checked handoff between GitHub Actions runners.

## Features

- A simple `/ping` slash command that responds with the bot's latency.
- Python 3.12 and `discord.py`.
- Manual startup with **Actions → Run Discord bot → Run workflow**.
- Runner handoff: a replacement runner starts before the current runner stops.
- A readiness marker confirms the replacement has connected to Discord before the previous runner shuts down.
- A scheduled recovery check looks for a missing runner chain every 30 minutes.

## Setup

1. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Add the bot to your server with the `bot` and `applications.commands` scopes.
3. In this GitHub repository, open **Settings → Secrets and variables → Actions**.
4. Create a repository secret named `DISCORD_TOKEN` containing the bot token. Never commit or share the token.
5. Create a fine-grained personal access token (PAT) limited to this repository, with **Actions: Read and write** permission. Save it as the repository secret `BOT_WORKFLOW_TOKEN`. The workflow uses this token to dispatch and inspect replacement runs. Never put the PAT in source code.
6. Open the **Actions** tab, enable workflows if prompted, then run **Run Discord bot** manually with the default input.
7. Invite the bot to a server and try `/ping`. Global slash-command registration can take a little while to propagate.

The `BOT_WORKFLOW_TOKEN` is required for the handoff and duplicate-run guard. If it is missing or lacks permission, the workflow will fail rather than silently pretending the handoff is working.

## Run locally

Install Python 3.12+, then:

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

Set `DISCORD_TOKEN` in your environment and run:

```bash
python bot.py
```

The `BOT_READY_FILE` environment variable is optional and is only used by the workflow to signal that the bot has connected to Discord.

## Runner handoff behavior

1. A runner starts the bot and waits for Discord's `on_ready` event.
2. At 5 hours 30 minutes after readiness, it dispatches a replacement run.
3. The replacement starts its bot, confirms it stays alive for a short stability window after its own `on_ready` event, then uploads a `bot-ready` artifact.
4. The old runner polls the replacement run and artifact. It stops its bot only after that readiness marker exists, so the new connection is established before the old one is shut down.
5. If a replacement fails before becoming ready, the old runner tries again. A safety deadline stops the old process at about 5 hours 42 minutes, leaving margin under GitHub's job timeout.
6. A scheduled check runs every 30 minutes. It exits if another runner is active and can start a new root run if the handoff chain has stopped.

The workflow intentionally has no global concurrency group: serializing runs would prevent the replacement from starting while the old runner is still active. Instead, the root-run guard avoids ordinary duplicate manual/scheduled starts, while handoff runs are allowed to overlap.

## Limitations

**This is best-effort runner handoff, not guaranteed 24/7 hosting.** GitHub may delay scheduled workflows, runners can fail, and Discord connectivity can drop. A handoff depends on the `BOT_WORKFLOW_TOKEN` remaining valid and authorized. Check the Actions logs if a handoff fails.

GitHub Actions is primarily a CI automation service, not a dedicated always-on application host. For dependable production uptime, use a host designed for long-running bot processes.

## Project layout

- `bot.py` — Discord client, readiness signal, and `/ping` command
- `requirements.txt` — Python dependencies
- `.github/workflows/bot.yml` — runner startup, handoff, and recovery check
