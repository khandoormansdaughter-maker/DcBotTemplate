"""Minimal Discord bot template with a /ping slash command."""
import os
from pathlib import Path

import discord
from discord import app_commands


TOKEN = os.getenv("DISCORD_TOKEN")
READY_FILE = os.getenv("BOT_READY_FILE")


class TemplateBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Register slash commands globally. Discord may take a little while to
        # propagate global command updates.
        await self.tree.sync()


bot = TemplateBot()


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # GitHub Actions uses this marker to confirm a replacement runner is
    # connected before the previous runner shuts down.
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")


@bot.tree.command(name="ping", description="Check whether the bot is responsive.")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓 ({latency_ms} ms)")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is missing. Add it as a GitHub Actions repository secret "
            "or set it in your local environment."
        )
    bot.run(TOKEN)
