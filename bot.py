"""Discord bot with optional Gemini-powered chat."""
import asyncio
import os
import logging
import time
import traceback
from collections import defaultdict, deque
from pathlib import Path

import discord
from discord import app_commands
from google import genai

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
READY_FILE = os.getenv("BOT_READY_FILE")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dollapp")
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
    logger.info("Discord ready: user_id=%s", bot.user.id)
    logger.info(
        "Gemini configuration: client_initialized=%s api_key_present=%s model=%s",
        gemini_client is not None,
        bool(GEMINI_API_KEY),
        GEMINI_MODEL,
    )
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")


def split_message(text, limit=1900):
    text = (text or "I couldn't generate a response.").strip()
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def log_gemini_error(exc):
    """Print actionable, redacted Gemini diagnostics for GitHub Actions logs."""
    detail = str(exc)
    if GEMINI_API_KEY:
        detail = detail.replace(GEMINI_API_KEY, "[REDACTED]")
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    # Include traceback for diagnosis, while redacting the secret from all logged text.
    trace = traceback.format_exc()
    if GEMINI_API_KEY:
        trace = trace.replace(GEMINI_API_KEY, "[REDACTED]")
    logger.error(
        "Gemini API request failed: exception_type=%s status=%s detail=%s\\n%s",
        type(exc).__name__, status, detail, trace,
    )
    lower = detail.lower()
    if status in (401, 403) or "unauthenticated" in lower or "permission_denied" in lower or "invalid api key" in lower:
        return "Gemini rejected the API key or its permissions. Verify GEMINI_API_KEY in GitHub Actions secrets and that the key is enabled for the Gemini API."
    if status == 429 or "resource_exhausted" in lower or "quota" in lower:
        return "Gemini quota or rate limit reached. Check the API quota for this key, then try again."
    if status == 404 or "not_found" in lower or ("model" in lower and "not found" in lower):
        return f"Gemini model {GEMINI_MODEL!r} is unavailable. Check the GEMINI_MODEL setting."
    if isinstance(status, int) and status >= 500:
        return "Gemini is temporarily having a server-side problem. Please try again shortly."
    return "Gemini request failed. Check the latest GitHub Actions log for the redacted API error details."


async def ask_gemini(prompt, history=None):
    if gemini_client is None:
        raise RuntimeError(
            "Gemini isn't configured. Add GEMINI_API_KEY under repository Settings → "
            "Secrets and variables → Actions, then restart the workflow."
        )

    request_started = time.monotonic()
    logger.info(
        "Gemini request starting: model=%s history_turns=%d prompt_chars=%d",
        GEMINI_MODEL, len(history or []), len(prompt),
    )

    # Use Google's Interactions API, matching the current official Python example.
    def generate():
        return gemini_client.interactions.create(
            model=GEMINI_MODEL,
            input=f"{SYSTEM_INSTRUCTION}\n\nConversation so far:\n" +
                  "\n".join(
                      f"{'User' if role == 'user' else 'Assistant'}: {content}"
                      for role, content in (history or [])
                  ) +
                  f"\n\nUser: {prompt}\nAssistant:",
        )

    try:
        response = await asyncio.to_thread(generate)
    except Exception:
        logger.exception(
            "Gemini interaction call raised after %.2fs (model=%s)",
            time.monotonic() - request_started, GEMINI_MODEL,
        )
        raise

    answer = (response.output_text or "").strip()
    logger.info(
        "Gemini request completed: elapsed_seconds=%.2f output_chars=%d output_present=%s",
        time.monotonic() - request_started, len(answer), bool(answer),
    )
    if not answer:
        logger.warning("Gemini returned an empty output_text; response_type=%s", type(response).__name__)
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

    logger.info(
        "Discord chat trigger: message_id=%s channel_id=%s author_id=%s mentioned=%s reply_to_bot=%s",
        message.id, message.channel.id, message.author.id, mentioned, replying_to_bot,
    )
    prompt = message.content.replace(f"<@{bot.user.id}>", "")
    prompt = prompt.replace(f"<@!{bot.user.id}>", "").strip()
    if not prompt:
        await message.reply("Ask me a question in your mention, reply to my message, or use /prompt.", mention_author=False)
        return

    history = histories[(message.channel.id, message.author.id)]
    try:
        async with message.channel.typing():
            answer = await ask_gemini(prompt, history)
        chunks = split_message(answer)
        logger.info("Sending Gemini response to Discord: message_id=%s chunks=%d", message.id, len(chunks))
        for chunk in chunks:
            await message.reply(chunk, mention_author=False)
    except RuntimeError as exc:
        logger.error("Gemini unavailable for Discord message %s: %s", message.id, exc)
        await message.reply(str(exc), mention_author=False)
    except Exception as exc:
        error_message = log_gemini_error(exc)
        await message.reply(error_message, mention_author=False)


@bot.tree.command(name="ping", description="Check whether the bot is responsive.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 ({round(bot.latency * 1000)} ms)")


@bot.tree.command(name="prompt", description="Ask Gemini a question.")
@app_commands.describe(prompt="What you want to ask Gemini")
async def prompt_command(interaction: discord.Interaction, prompt: str):
    logger.info(
        "Discord /prompt invoked: interaction_id=%s channel_id=%s user_id=%s prompt_chars=%d",
        interaction.id, interaction.channel_id, interaction.user.id, len(prompt),
    )
    await interaction.response.defer(thinking=True)
    history = histories[(interaction.channel_id or 0, interaction.user.id)]
    try:
        answer = await ask_gemini(prompt, history)
        for chunk in split_message(answer):
            await interaction.followup.send(chunk)
    except RuntimeError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
    except Exception as exc:
        error_message = log_gemini_error(exc)
        await interaction.followup.send(error_message, ephemeral=True)


if __name__ == "__main__":
    logger.info(
        "Starting DollAPP: discord_token_present=%s gemini_api_key_present=%s model=%s log_level=%s",
        bool(TOKEN), bool(GEMINI_API_KEY), GEMINI_MODEL, logging.getLevelName(logger.getEffectiveLevel()),
    )
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing; set it as a repository secret or environment variable.")
    try:
        bot.run(TOKEN)
    except Exception:
        logger.exception("Discord bot process exited with an exception")
        raise
