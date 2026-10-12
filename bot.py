"""Discord bot template with lightweight natural-language server actions."""
import os
import re
from pathlib import Path

import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
READY_FILE = os.getenv("BOT_READY_FILE")

CREATE_CHANNEL_PATTERNS = (
    re.compile(
        r"\b(?:create|make|add)\s+(?:a\s+)?(?:text\s+)?channel\s+"
        r"(?:named|called)\s+[\"'“”]?([a-zA-Z0-9][a-zA-Z0-9 _-]{0,89})[\"'“”]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:create|make|add)\s+(?:a\s+)?channel\s+"
        r"[\"'“”]([a-zA-Z0-9][a-zA-Z0-9 _-]{0,89})[\"'“”]",
        re.IGNORECASE,
    ),
)


def extract_intent(message: str) -> tuple[str, str] | None:
    """Return (intent, argument) when a supported request is recognized."""
    for pattern in CREATE_CHANNEL_PATTERNS:
        match = pattern.search(message)
        if match:
            name = re.sub(r"\s+", "-", match.group(1).strip()).strip("-").lower()
            if name:
                return ("create_text_channel", name[:100])
    return None


class TemplateBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()


bot = TemplateBot()


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or message.guild is None:
        return

    addressed = bot.user is not None and (
        bot.user in message.mentions
        or message.content.lower().startswith(("hey doll", "doll,"))
    )
    if not addressed:
        return

    intent = extract_intent(message.content)
    if intent is None:
        await message.reply(
            "I couldn't identify a supported action yet. Try: "
            '"Hey doll, can you create a channel named hello thanks."',
            mention_author=False,
        )
        return

    action, channel_name = intent
    if action == "create_text_channel":
        guild = message.guild
        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_channels:
            await message.reply(
                "I can't create channels because I don't have the Manage Channels permission.",
                mention_author=False,
            )
            return

        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing is not None:
            await message.reply(
                f"A text channel named {existing.mention} already exists.",
                mention_author=False,
            )
            return

        try:
            channel = await guild.create_text_channel(
                channel_name,
                reason=f"Requested by {message.author} via SllBot",
            )
        except discord.Forbidden:
            await message.reply(
                "Discord denied that action. Please check my role and channel-management permissions.",
                mention_author=False,
            )
        except discord.HTTPException:
            await message.reply(
                "Discord couldn't create the channel just now. Please try again.",
                mention_author=False,
            )
        else:
            await message.reply(f"Done — created {channel.mention}.", mention_author=False)


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
