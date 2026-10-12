# SllBot

SllBot is a lightweight Discord server-action bot. It reads addressed messages, extracts supported intents, checks permissions, and performs allowlisted actions. It does not use speech recognition or text-to-speech.

Supported actions on the SllBot branch are text-channel creation. Planned extensions include roles, forum channels, threads, and carefully permission-gated moderation.

Enable Message Content Intent in the Discord Developer Portal. Store DISCORD_TOKEN as a repository secret. Grant only the permissions the bot needs. The bot cannot bypass Discord permissions or role hierarchy.
