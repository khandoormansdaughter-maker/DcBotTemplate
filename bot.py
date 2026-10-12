"""Discord bot with fast Gemini-powered chat and per-user character prompts."""
import asyncio
import logging
import os
import time
import traceback
from collections import defaultdict, deque
from pathlib import Path

import discord
from discord import app_commands
from google import genai
from google.genai import types

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "30000"))
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "700"))
READY_FILE = os.getenv("BOT_READY_FILE")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dollapp")
SYSTEM_INSTRUCTION = "You are a helpful, friendly, concise assistant chatting in a Discord server."
histories = defaultdict(lambda: deque(maxlen=12))
# A character prompt is scoped to one user in one channel, so one user's persona
# won't unexpectedly change how the bot responds to somebody else.
character_prompts = {}
gemini_client = (
    genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=GEMINI_TIMEOUT_MS,
            # Google's SDK defaults to as many as five attempts with long backoff.
            # Two attempts keeps recovery from brief 503s while avoiding long stalls.
            retry_options=types.HttpRetryOptions(
                attempts=2,
                initial_delay=0.25,
                max_delay=1.0,
                exp_base=2.0,
                jitter=0.1,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        ),
    )
    if GEMINI_API_KEY
    else None
)


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
        "Gemini configuration: client_initialized=%s api_key_present=%s model=%s timeout_ms=%s max_output_tokens=%s",
        gemini_client is not None,
        bool(GEMINI_API_KEY),
        GEMINI_MODEL,
        GEMINI_TIMEOUT_MS,
        GEMINI_MAX_OUTPUT_TOKENS,
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
    trace = traceback.format_exc()
    if GEMINI_API_KEY:
        trace = trace.replace(GEMINI_API_KEY, "[REDACTED]")
    logger.error(
        "Gemini API request failed: exception_type=%s status=%s detail=%s\n%s",
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


def get_character_key(channel_id, user_id):
    return (channel_id or 0, user_id)


async def ask_gemini(prompt, history=None, character_prompt=None):
    if gemini_client is None:
        raise RuntimeError(
            "Gemini isn't configured. Add GEMINI_API_KEY under repository Settings → "
            "Secrets and variables → Actions, then restart the workflow."
        )

    request_started = time.monotonic()
    system_instruction = SYSTEM_INSTRUCTION
    if character_prompt:
        system_instruction += (
            "\n\nFollow this character/persona instruction unless it conflicts with safety rules:\n"
            + character_prompt
        )
    conversation = "\n".join(
        f"{'User' if role == 'user' else 'Assistant'}: {content}"
        for role, content in (history or [])
    )
    request_input = (f"Conversation so far:\n{conversation}\n\n" if conversation else "") + f"User: {prompt}\nAssistant:"
    logger.info(
        "Gemini request starting: model=%s history_turns=%d prompt_chars=%d persona_set=%s",
        GEMINI_MODEL, len(history or []), len(prompt), bool(character_prompt),
    )

    def generate():
        return gemini_client.interactions.create(
            model=GEMINI_MODEL,
            system_instruction=system_instruction,
            input=request_input,
            generation_config={"max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS},
        )

    try:
        response = await asyncio.to_thread(generate)
    except Exception as exc:
        logger.error(
            "Gemini interaction call raised after %.2fs (model=%s)",
            time.monotonic() - request_started, GEMINI_MODEL,
        )
        log_gemini_error(exc)
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


async def send_answer(channel, prompt, channel_id, user_id, reply_to=None):
    key = get_character_key(channel_id, user_id)
    history = histories[key]
    character = character_prompts.get(key)
    async with channel.typing():
        answer = await ask_gemini(prompt, history, character)
    chunks = split_message(answer)
    logger.info("Sending Gemini response: chunks=%d persona_set=%s", len(chunks), bool(character))
    for chunk in chunks:
        if reply_to is not None:
            await reply_to.reply(chunk, mention_author=False)
        else:
            await channel.send(chunk)


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
        await message.reply("Ask me something in your mention or reply, or set my character with /prompt.", mention_author=False)
        return

    try:
        await send_answer(message.channel, prompt, message.channel.id, message.author.id, reply_to=message)
    except RuntimeError as exc:
        logger.error("Gemini unavailable for Discord message %s: %s", message.id, exc)
        await message.reply(str(exc), mention_author=False)
    except Exception as exc:
        await message.reply(log_gemini_error(exc), mention_author=False)


@bot.tree.command(name="ping", description="Check whether the bot is responsive.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 ({round(bot.latency * 1000)} ms)")


@bot.tree.command(name="prompt", description="Set the character/persona Gemini should act as.")
@app_commands.describe(character="Describe the character, personality, and behavior to follow")
async def prompt_command(interaction: discord.Interaction, character: str):
    character = character.strip()
    if not character:
        await interaction.response.send_message("Please enter a character or persona prompt.", ephemeral=True)
        return
    if len(character) > 1500:
        await interaction.response.send_message("Keep the character prompt under 1,500 characters.", ephemeral=True)
        return

    key = get_character_key(interaction.channel_id, interaction.user.id)
    character_prompts[key] = character
    histories[key].clear()
    logger.info(
        "Discord /prompt set persona: interaction_id=%s channel_id=%s user_id=%s character_chars=%d",
        interaction.id, interaction.channel_id, interaction.user.id, len(character),
    )
    await interaction.response.send_message(
        "Character prompt saved for you in this channel. Mention me, reply to one of my messages, or use /ask to chat in character. Your previous chat history for this channel was cleared.",
        ephemeral=True,
    )


@bot.tree.command(name="ask", description="Ask Gemini a question using your current character prompt.")
@app_commands.describe(question="What you want to ask Gemini")
async def ask_command(interaction: discord.Interaction, question: str):
    key = get_character_key(interaction.channel_id, interaction.user.id)
    logger.info(
        "Discord /ask invoked: interaction_id=%s channel_id=%s user_id=%s prompt_chars=%d persona_set=%s",
        interaction.id, interaction.channel_id, interaction.user.id, len(question), key in character_prompts,
    )
    await interaction.response.defer(thinking=True)
    try:
        await send_answer(interaction.channel, question, interaction.channel_id, interaction.user.id)
        # send_answer posts to the channel; the interaction acknowledgement is deferred above.
        await interaction.followup.send("Done.", ephemeral=True)
    except RuntimeError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(log_gemini_error(exc), ephemeral=True)


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
