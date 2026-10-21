"""User-installed Discord translation app for the Translator branch.

This app responds to commands and message-context-menu actions. It does not
read the server's message stream or automate a personal Discord account.
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
            return value
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"users": {}}


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
        # No message-content or message-event intents are needed for interaction-only apps.
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = TranslatorBot()


@bot.event
async def on_ready():
    print(f"Translator app connected as {bot.user} (ID: {bot.user.id})")
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")


@bot.tree.command(name="ping", description="Check whether Translator is responding.")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! 🏓 ({round(bot.latency * 1000)} ms)", ephemeral=True
    )


@bot.tree.command(name="translate", description="Translate text into your preferred language.")
@app_commands.describe(text="Text to translate")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def translate_command(interaction: discord.Interaction, text: str):
    destination = target_language(interaction.user.id)
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        translated, source = await translate(text, destination)
        await interaction.followup.send(
            f"**Translation** ({source} → {destination}):\n{translated}", ephemeral=True
        )
    except Exception as exc:
        print(f"Translation failed: {exc}")
        await interaction.followup.send(
            "Translation failed. Please try again later.", ephemeral=True
        )


@bot.tree.context_menu(name="Translate message")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def translate_message(interaction: discord.Interaction, message: discord.Message):
    # Discord provides the selected message in this interaction; no message history
    # or ongoing access to the channel is requested.
    if not message.content or not message.content.strip():
        await interaction.response.send_message(
            "That message has no translatable text. Messages made only of attachments "
            "or embeds may not include text for this command.",
            ephemeral=True,
        )
        return

    destination = target_language(interaction.user.id)
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        translated, source = await translate(message.content, destination)
        await interaction.followup.send(
            f"**{message.author.display_name}** wrote ({source} → {destination}):\n{translated}",
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )
    except Exception as exc:
        print(f"Message translation failed: {exc}")
        await interaction.followup.send(
            "Translation failed. Please try again later.", ephemeral=True
        )


@bot.tree.command(name="language", description="Set your preferred translation language.")
@app_commands.describe(language="Google Translate language code, e.g. en, es, fr, ja, or de")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
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
    await interaction.response.send_message(
        f"Your translation language is now **{language}**.", ephemeral=True
    )


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Set it as a GitHub Actions repository secret.")
    bot.run(TOKEN)
