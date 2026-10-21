"""Discord translation bot for the Translator branch.

Uses an official Discord bot application, not a personal-account self-bot.
"""
import asyncio
import json
import os
from pathlib import Path

import discord
from discord import app_commands
from googletrans import Translator

TOKEN = os.getenv("DISCORD_TOKEN")
READY_FILE = os.getenv("BOT_READY_FILE")
SETTINGS_FILE = Path(os.getenv("TRANSLATOR_SETTINGS_FILE", "translator_settings.json"))
translator = Translator()
settings_lock = asyncio.Lock()


def load_settings():
    try:
        value = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value.setdefault("users", {})
            value.setdefault("channels", {})
            return value
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"users": {}, "channels": {}}


settings = load_settings()


async def save_settings():
    async with settings_lock:
        SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def target_language(user_id: int) -> str:
    return settings["users"].get(str(user_id), {}).get("language", "en")


async def translate(text: str, destination: str):
    result = await translator.translate(text, dest=destination)
    return result.text, result.src


class TranslatorBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = TranslatorBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")


@bot.tree.command(name="ping", description="Check whether the bot is responsive.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 ({round(bot.latency * 1000)} ms)")


@bot.tree.command(name="translate", description="Translate text into your preferred language.")
@app_commands.describe(text="Text to translate")
async def translate_command(interaction: discord.Interaction, text: str):
    destination = target_language(interaction.user.id)
    await interaction.response.defer(thinking=True)
    try:
        translated, source = await translate(text, destination)
        await interaction.followup.send(f"**Translation** ({source} → {destination}):\n{translated}")
    except Exception as exc:
        print(f"Translation failed: {exc}")
        await interaction.followup.send("Translation failed. Please try again later.", ephemeral=True)


@bot.tree.context_menu(name="Translate message")
async def translate_message(interaction: discord.Interaction, message: discord.Message):
    if not message.content.strip():
        await interaction.response.send_message("That message has no translatable text.", ephemeral=True)
        return
    destination = target_language(interaction.user.id)
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        translated, source = await translate(message.content, destination)
        await interaction.followup.send(
            f"**{message.author.display_name}** wrote ({source} → {destination}):\n{translated}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception as exc:
        print(f"Message translation failed: {exc}")
        await interaction.followup.send("Translation failed. Please try again later.", ephemeral=True)


@bot.tree.command(name="language", description="Set your preferred translation language.")
@app_commands.describe(language="Google Translate language code, e.g. en, es, fr, ja, or de")
async def language_command(interaction: discord.Interaction, language: str = "en"):
    language = language.strip().lower()
    try:
        # Ask Google Translate to validate the destination code.
        await translate("Hello", language)
    except Exception:
        await interaction.response.send_message(
            "I couldn't validate that language code. Try en, es, fr, de, ja, or zh-cn.",
            ephemeral=True,
        )
        return
    settings["users"].setdefault(str(interaction.user.id), {})["language"] = language
    await save_settings()
    await interaction.response.send_message(f"Your translation language is now **{language}**.", ephemeral=True)


@bot.tree.command(name="channel", description="Enable automatic translation in a channel.")
@app_commands.describe(channel="Text channel to monitor", language="Destination language (default: en)")
@app_commands.default_permissions(manage_channels=True)
async def channel_command(
    interaction: discord.Interaction, channel: discord.TextChannel, language: str = "en"
):
    language = language.strip().lower()
    try:
        await translate("Hello", language)
    except Exception:
        await interaction.response.send_message("Invalid or unavailable language code.", ephemeral=True)
        return
    settings["channels"][str(channel.id)] = {"language": language}
    await save_settings()
    await interaction.response.send_message(
        f"Automatic translation enabled in {channel.mention} → **{language}**.", ephemeral=True
    )


@bot.tree.command(name="channel_off", description="Disable automatic translation in a channel.")
@app_commands.describe(channel="Channel to stop monitoring")
@app_commands.default_permissions(manage_channels=True)
async def channel_off_command(interaction: discord.Interaction, channel: discord.TextChannel):
    settings["channels"].pop(str(channel.id), None)
    await save_settings()
    await interaction.response.send_message(
        f"Automatic translation disabled in {channel.mention}.", ephemeral=True
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild or not message.content.strip():
        return
    config = settings["channels"].get(str(message.channel.id))
    if not config:
        return
    destination = config.get("language", "en")
    try:
        translated, source = await translate(message.content, destination)
        # Skip messages already written in the configured destination language.
        if source.lower().split("-")[0] == destination.lower().split("-")[0]:
            return
        await message.reply(
            f"**{message.author.display_name}** ({source} → {destination}):\n{translated}",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception as exc:
        print(f"Automatic translation failed for message {message.id}: {exc}")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Set it as a GitHub Actions repository secret.")
    bot.run(TOKEN)
