"""Discord bot with optional Gemini-powered chat."""
import asyncio
import os
from collections import defaultdict, deque
from pathlib import Path

import discord
from discord import app_commands
from google import genai

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
READY_FILE = os.getenv("BOT_READY_FILE")
SYSTEM_INSTRUCTION = "You are a helpful, friendly, concise assistant chatting in a Discord server."
histories = defaultdict(lambda: deque(maxlen=12))
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


class TemplateBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = TemplateBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Gemini chat enabled (model: {GEMINI_MODEL})." if gemini_client else "Gemini disabled: set GEMINI_API_KEY.")
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")


def split_message(text, limit=1900):
    text = (text or "I couldn't generate a response.").strip()
    return [text[i:i + limit] for i in range(0, len(text), limit)]


async def ask_gemini(prompt, history=None):
    if gemini_client is None:
        raise RuntimeError(
            "Gemini isn't configured. Add GEMINI_API_KEY under repository Settings → "
            "Secrets and variables → Actions, then restart the workflow."
        )
    contents = [
        {"role": role, "parts": [{"text": content}]}
        for role, content in (history or [])
    ]
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    def generate():
        return gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config={"system_instruction": SYSTEM_INSTRUCTION},
        )

    response = await asyncio.to_thread(generate)
    answer = (response.text or "").strip()
    if not answer:
        answer = "Gemini returned an empty response. Try asking another way."
    if history is not None:
        history.append(("user", prompt))
        history.append(("model", answer))
    return answer


@bot.event
async def on_message(message):
    if message.author.bot or bot.user is None:
        return
    mentioned = bot.user in message.mentions
    replying_to_bot = False
    if message.reference and message.reference.message_id:
        try:
            referenced = message.reference.resolved
            if referenced is None:
                referenced = await message.channel.fetch_message(message.reference.message_id)
            replying_to_bot = referenced.author.id == bot.user.id
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
    if not (mentioned or replying_to_bot):
        return

    prompt = message.content.replace(f"<@{bot.user.id}>", "")
    prompt = prompt.replace(f"<@!{bot.user.id}>", "").strip()
    if not prompt:
        await message.reply("Ask me a question in your mention, reply to my message, or use /prompt.", mention_author=False)
        return

    history = histories[(message.channel.id, message.author.id)]
    try:
        async with message.channel.typing():
            answer = await ask_gemini(prompt, history)
        for chunk in split_message(answer):
            await message.reply(chunk, mention_author=False)
    except RuntimeError as exc:
        await message.reply(str(exc), mention_author=False)
    except Exception as exc:
        print(f"Gemini request failed ({type(exc).__name__}): {exc}")
        await message.reply("I couldn't reach Gemini. Check the bot logs and API key, then try again.", mention_author=False)


@bot.tree.command(name="ping", description="Check whether the bot is responsive.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 ({round(bot.latency * 1000)} ms)")


@bot.tree.command(name="prompt", description="Ask Gemini a question.")
@app_commands.describe(prompt="What you want to ask Gemini")
async def prompt_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    history = histories[(interaction.channel_id or 0, interaction.user.id)]
    try:
        answer = await ask_gemini(prompt, history)
        for chunk in split_message(answer):
            await interaction.followup.send(chunk)
    except RuntimeError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
    except Exception as exc:
        print(f"Gemini request failed ({type(exc).__name__}): {exc}")
        await interaction.followup.send("I couldn't reach Gemini. Check the bot logs and API key, then try again.", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing; set it as a repository secret or environment variable.")
    bot.run(TOKEN)
