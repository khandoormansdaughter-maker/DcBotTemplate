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
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "15000"))
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
            # Disable the SDK's long automatic backoff; ask_gemini owns a
            # single quick retry below so failures cannot stall for minutes.
            retry_options=types.HttpRetryOptions(
                attempts=1,
                initial_delay=0.1,
                max_delay=0.2,
                exp_base=2.0,
                jitter=0.0,
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

    response = None
    for attempt in range(1, 3):
        attempt_started = time.monotonic()
        try:
            response = await asyncio.to_thread(generate)
            if attempt > 1:
                logger.info("Gemini quick retry succeeded on attempt %d", attempt)
            break
        except Exception as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            detail = str(exc).lower()
            retryable_status = status in (408, 429, 500, 502, 503, 504)
            retryable_timeout = (
                "timeout" in type(exc).__name__.lower()
                or "timed out" in detail
                or isinstance(exc, TimeoutError)
            )
            if attempt == 1 and (retryable_status or retryable_timeout):
                logger.warning(
                    "Gemini transient failure; retrying once quickly: status=%s exception_type=%s attempt_seconds=%.2f",
                    status, type(exc).__name__, time.monotonic() - attempt_started,
                )
                await asyncio.sleep(0.4)
                continue

            logger.error(
                "Gemini interaction call failed after %.2fs total (model=%s attempts=%d)",
                time.monotonic() - request_started, GEMINI_MODEL, attempt,
            )
            log_gemini_error(exc)
            raise

    if response is None:
        raise RuntimeError("Gemini did not return a response after the retry.")

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


# Natural-language server actions use an allowlist and require an explicit
# confirmation from the moderator who requested the change.
reply_channels = {}


def _member_from_mention(guild, token):
    import re
    match = re.fullmatch(r"<@!?(\d+)>", token.strip())
    return guild.get_member(int(match.group(1))) if match else None


def _channel_from_token(guild, token):
    import re
    match = re.fullmatch(r"<#(\d+)>", token.strip())
    if match:
        return guild.get_channel(int(match.group(1)))
    return discord.utils.get(guild.channels, name=token.strip().lstrip("#").casefold())


def _role_from_token(guild, token):
    import re
    match = re.fullmatch(r"<@&(\d+)>", token.strip())
    if match:
        return guild.get_role(int(match.group(1)))
    return discord.utils.get(guild.roles, name=token.strip().lstrip("@").casefold())


def _parse_server_action(guild, content, bot_user_id):
    import re
    text = re.sub(r"<@!?" + str(bot_user_id) + r">", "", content).strip()

    # Creating a discussion post in an existing forum channel.
    match = re.search(r"\b(?:create|make|post)\s+(?:a\s+)?(?:forum\s+)?post\s+in\s+(<#\d+>)\s+(?:titled|called|named)\s+['\"]?(.{1,100}?)['\"]?\s*(?::|-\s+|\bsaying\b)\s*(.{1,1800})$", text, re.I | re.S)
    if match:
        channel = _channel_from_token(guild, match.group(1))
        title = match.group(2).strip(" '\"")[:100]
        body = match.group(3).strip().strip("'\"")[:1800]
        if isinstance(channel, discord.ForumChannel) and title and body:
            return {"kind": "forum_post", "channel_id": channel.id, "title": title, "body": body,
                    "summary": f"Create a post titled **{title}** in forum **{channel.name}**"}

    match = re.search(r"\b(?:create|make)\s+(?:a\s+)?(text\s+channel|channel|forum|voice\s+channel|category)\s+(?:called|named|as)\s+(.{1,90})$", text, re.I)
    if match:
        channel_type = match.group(1).lower()
        name = match.group(2).strip(" #'\"")[:90]
        if name:
            return {"kind": "create_channel", "channel_type": channel_type, "name": name,
                    "summary": f"Create a {channel_type} named **{name}**"}

    match = re.search(r"\b(?:create|make)\s+(?:a\s+)?role\s+(?:called|named|as)\s+(.{1,90})$", text, re.I)
    if match:
        name = match.group(1).strip(" #'\"")[:90]
        if name:
            return {"kind": "create_role", "name": name, "summary": f"Create role **{name}**"}

    match = re.search(r"\b(?:move|put)\s+(<#\d+>)\s+(?:into|under|to)\s+(?:the\s+)?(?:category\s+)?(.{1,90})$", text, re.I)
    if match:
        channel = _channel_from_token(guild, match.group(1))
        category = _channel_from_token(guild, match.group(2).strip(" #'\""))
        if channel and isinstance(category, discord.CategoryChannel):
            return {"kind": "move_channel", "channel_id": channel.id, "category_id": category.id,
                    "summary": f"Move **{channel.name}** into category **{category.name}**"}

    match = re.search(r"\b(?:restrict|lock|limit)\s+(<#\d+>)\s+(?:to|for)\s+(<@&\d+>)", text, re.I)
    if match:
        channel = _channel_from_token(guild, match.group(1))
        role = _role_from_token(guild, match.group(2))
        if channel and role and role != guild.default_role:
            return {"kind": "restrict_channel", "channel_id": channel.id, "role_id": role.id,
                    "summary": f"Restrict **{channel.name}** to role **{role.name}**"}

    match = re.search(r"\b(?:send|put|route)\s+(?:your\s+)?(?:replies|responses|answers)\s+(?:in|to|into)\s+(<#\d+>)", text, re.I)
    if match:
        channel = _channel_from_token(guild, match.group(1))
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return {"kind": "set_reply_channel", "channel_id": channel.id,
                    "summary": f"Send future replies in **{channel.name}**"}

    # Moderation and role assignment intentionally require explicit member/role mentions.
    match = re.search(r"\b(kick|ban)\s+(<@!?\d+>)", text, re.I)
    if match:
        member = _member_from_mention(guild, match.group(2))
        if member and member.id != guild.owner_id and member.id != bot_user_id:
            return {"kind": match.group(1).lower(), "member_id": member.id,
                    "summary": f"{match.group(1).title()} **{member.display_name}**"}

    match = re.search(r"\b(?:give|assign|add)\s+(<@!?\d+>)\s+(?:the\s+)?role\s+(<@&\d+>)", text, re.I)
    if match:
        member = _member_from_mention(guild, match.group(1))
        role = _role_from_token(guild, match.group(2))
        if member and role and role != guild.default_role and member.id != bot_user_id:
            return {"kind": "assign_role", "member_id": member.id, "role_id": role.id,
                    "summary": f"Assign **{role.name}** to **{member.display_name}**"}

    match = re.search(r"\b(?:remove|take)\s+(<@&\d+>)\s+from\s+(<@!?\d+>)", text, re.I)
    if match:
        role = _role_from_token(guild, match.group(1))
        member = _member_from_mention(guild, match.group(2))
        if member and role and role != guild.default_role and member.id != bot_user_id:
            return {"kind": "remove_role", "member_id": member.id, "role_id": role.id,
                    "summary": f"Remove **{role.name}** from **{member.display_name}**"}
    return None


def _required_permission(kind):
    if kind in ("create_role", "assign_role", "remove_role"):
        return "manage_roles"
    if kind == "kick":
        return "kick_members"
    if kind == "ban":
        return "ban_members"
    return "manage_channels"


async def _apply_server_action(guild, action):
    kind = action["kind"]
    me = guild.me
    if kind == "set_reply_channel":
        channel = guild.get_channel(action["channel_id"])
        if channel is None or not channel.permissions_for(me).send_messages:
            raise PermissionError("I cannot send messages in that channel.")
        reply_channels[guild.id] = channel.id
        return f"My future mention/reply responses in this server will be sent in {channel.mention}. This setting resets when I restart."

    if kind == "create_channel":
        if not me.guild_permissions.manage_channels:
            raise PermissionError("I need Manage Channels.")
        name = action["name"]
        channel_type = action["channel_type"]
        if channel_type in ("channel", "text channel"):
            channel = await guild.create_text_channel(name, reason="Confirmed server-management request")
        elif channel_type == "forum":
            channel = await guild.create_forum(name, reason="Confirmed server-management request")
        elif channel_type == "voice channel":
            channel = await guild.create_voice_channel(name, reason="Confirmed server-management request")
        else:
            channel = await guild.create_category(name, reason="Confirmed server-management request")
        return f"Created {channel.mention if hasattr(channel, 'mention') else channel.name}."

    if kind == "forum_post":
        if not me.guild_permissions.manage_channels:
            raise PermissionError("I need Manage Channels to create forum posts.")
        channel = guild.get_channel(action["channel_id"])
        if not isinstance(channel, discord.ForumChannel):
            raise ValueError("That forum channel no longer exists.")
        forum_permissions = channel.permissions_for(me)
        if not forum_permissions.send_messages or not forum_permissions.create_public_threads:
            raise PermissionError("I need Send Messages and Create Public Threads in that forum.")
        created = await channel.create_thread(
            name=action["title"], content=action["body"],
            reason="Confirmed forum-post request",
        )
        thread = getattr(created, "thread", created)
        return f"Created forum post **{action['title']}**: {thread.mention}"

    if kind == "create_role":
        if not me.guild_permissions.manage_roles:
            raise PermissionError("I need Manage Roles.")
        role = await guild.create_role(name=action["name"], reason="Confirmed server-management request")
        return f"Created role **{role.name}**."

    if kind == "move_channel":
        if not me.guild_permissions.manage_channels:
            raise PermissionError("I need Manage Channels.")
        channel = guild.get_channel(action["channel_id"])
        category = guild.get_channel(action["category_id"])
        if channel is None or not isinstance(category, discord.CategoryChannel):
            raise ValueError("The channel or category no longer exists.")
        await channel.edit(category=category, reason="Confirmed server-management request")
        return f"Moved **{channel.name}** into **{category.name}**."

    if kind == "restrict_channel":
        if not me.guild_permissions.manage_channels:
            raise PermissionError("I need Manage Channels.")
        channel = guild.get_channel(action["channel_id"])
        role = guild.get_role(action["role_id"])
        if channel is None or role is None or role == guild.default_role:
            raise ValueError("The channel or role no longer exists.")
        overwrites = dict(channel.overwrites)
        everyone = overwrites.get(guild.default_role, discord.PermissionOverwrite())
        everyone.view_channel = False
        overwrites[guild.default_role] = everyone
        access = overwrites.get(role, discord.PermissionOverwrite())
        access.view_channel = True
        access.send_messages = True
        overwrites[role] = access
        await channel.edit(overwrites=overwrites, reason="Confirmed server-management request")
        return f"Restricted **{channel.name}** to **{role.name}** plus any other explicitly permitted roles or members."

    if kind in ("kick", "ban"):
        required = "kick_members" if kind == "kick" else "ban_members"
        if not getattr(me.guild_permissions, required):
            raise PermissionError(f"I need {required.replace('_', ' ').title()}.")
        member = guild.get_member(action["member_id"])
        if member is None:
            raise ValueError("That member is no longer in the server.")
        if member.id == guild.owner_id or member.id == me.id or member.top_role >= me.top_role:
            raise PermissionError("Discord's role hierarchy prevents me from moderating that member.")
        if kind == "kick":
            await member.kick(reason="Confirmed server-moderation request")
            return f"Kicked **{member.display_name}**."
        await guild.ban(member, reason="Confirmed server-moderation request", delete_message_seconds=0)
        return f"Banned **{member.display_name}**."

    if kind in ("assign_role", "remove_role"):
        if not me.guild_permissions.manage_roles:
            raise PermissionError("I need Manage Roles.")
        member = guild.get_member(action["member_id"])
        role = guild.get_role(action["role_id"])
        if member is None or role is None or role == guild.default_role:
            raise ValueError("The member or role no longer exists.")
        if role >= me.top_role or member.id == guild.owner_id or member.top_role >= me.top_role:
            raise PermissionError("Discord's role hierarchy prevents me from changing this member's roles.")
        if kind == "assign_role":
            await member.add_roles(role, reason="Confirmed role-assignment request")
            return f"Assigned **{role.name}** to **{member.display_name}**."
        await member.remove_roles(role, reason="Confirmed role-removal request")
        return f"Removed **{role.name}** from **{member.display_name}**."
    raise ValueError("That server action is not supported.")


class ServerActionConfirm(discord.ui.View):
    def __init__(self, requester_id, action):
        super().__init__(timeout=60)
        self.requester_id = requester_id
        self.action = action

    @discord.ui.button(label="Confirm change", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Only the person who requested this can confirm it.", ephemeral=True)
            return
        permission = _required_permission(self.action["kind"])
        if not getattr(interaction.user.guild_permissions, permission, False):
            await interaction.response.send_message(f"You need {permission.replace('_', ' ').title()} to confirm this.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            result = await _apply_server_action(interaction.guild, self.action)
            logger.info("Server action completed: guild_id=%s user_id=%s kind=%s", interaction.guild_id, interaction.user.id, self.action["kind"])
            await interaction.followup.send(result)
        except (discord.Forbidden, discord.HTTPException, PermissionError, ValueError) as exc:
            logger.warning("Server action failed: guild_id=%s kind=%s error=%s", interaction.guild_id, self.action["kind"], exc)
            await interaction.followup.send(f"Couldn't complete that change: {exc}")
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Only the person who requested this can cancel it.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Cancelled. No server changes were made.", view=self)
        self.stop()


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

    if message.guild:
        action = _parse_server_action(message.guild, message.content, bot.user.id)
        if action is not None:
            permission = _required_permission(action["kind"])
            if not getattr(message.author.guild_permissions, permission, False):
                await message.reply(
                    f"I understood that as a server-management request, but you need {permission.replace('_', ' ').title()} to request it.",
                    mention_author=False,
                )
                return
            await message.reply(
                f"Please confirm: {action['summary']}?\nRequired permission: {permission.replace('_', ' ').title()}.",
                view=ServerActionConfirm(message.author.id, action),
                mention_author=False,
            )
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

    target_channel = None
    if message.guild and message.guild.id in reply_channels:
        target_channel = bot.get_channel(reply_channels[message.guild.id])
        if target_channel is None:
            reply_channels.pop(message.guild.id, None)
    response_channel = target_channel or message.channel
    response_message = message if response_channel.id == message.channel.id else None
    try:
        await send_answer(response_channel, prompt, message.channel.id, message.author.id, reply_to=response_message)
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
        answer = await ask_gemini(question, histories[key], character_prompts.get(key))
        for chunk in split_message(answer):
            await interaction.followup.send(chunk)
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
