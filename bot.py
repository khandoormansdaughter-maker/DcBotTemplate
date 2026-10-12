import os
import re
from pathlib import Path
import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
READY_FILE = os.getenv("BOT_READY_FILE")

def extract_intent(text):
    rules = [
        ("create_forum", r"\b(?:create|make|add)\s+(?:a\s+)?forum\s+(?:named|called)\s+[\"']?([\w -]+?)[\"']?(?=\s+(?:please|thanks|thank you)\b|[.!?,;]|$)", True),
        ("create_thread", r"\b(?:create|make|start|open)\s+(?:a\s+)?thread\s+(?:named|called)\s+[\"']?([\w -]+?)[\"']?(?=\s+(?:please|thanks|thank you)\b|[.!?,;]|$)", False),
        ("create_role", r"\b(?:create|make|add)\s+(?:a\s+)?role\s+(?:named|called)\s+[\"']?([\w -]+?)[\"']?(?=\s+(?:please|thanks|thank you)\b|[.!?,;]|$)", False),
        ("create_text_channel", r"\b(?:create|make|add)\s+(?:a\s+)?(?:text\s+)?channel\s+(?:named|called)\s+[\"']?([\w -]+?)[\"']?(?=\s+(?:please|thanks|thank you)\b|[.!?,;]|$)", True),
    ]
    for action, pattern, slug in rules:
        match = re.search(pattern, text, re.I)
        if match:
            name = re.sub(r"\s+", " ", match.group(1)).strip(" \"'")
            if slug:
                name = re.sub(r"\s+", "-", name).lower()
            if name:
                return action, name[:100]
    return None

class SllBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()

bot = SllBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if READY_FILE:
        Path(READY_FILE).write_text("ready\n", encoding="utf-8")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild or not bot.user:
        return
    if bot.user not in message.mentions and not message.content.lower().startswith(("hey doll", "doll,", "doll ")):
        return
    intent = extract_intent(message.content)
    if not intent:
        await message.reply("I can create text channels, forum channels, threads, and roles. Please name the item.", mention_author=False)
        return
    action, name = intent
    guild = message.guild
    actor = message.author if isinstance(message.author, discord.Member) else None
    me = guild.me
    if not actor or not me:
        return
    reason = f"Requested by {actor} via SllBot"
    try:
        if action in ("create_text_channel", "create_forum"):
            if not actor.guild_permissions.manage_channels or not me.guild_permissions.manage_channels:
                await message.reply("You and I both need Manage Channels permission.", mention_author=False)
                return
            if action == "create_text_channel":
                if discord.utils.get(guild.text_channels, name=name):
                    await message.reply("That text channel already exists.", mention_author=False)
                    return
                created = await guild.create_text_channel(name, reason=reason)
            else:
                if not hasattr(guild, "create_forum"):
                    await message.reply("Please update discord.py to enable forum creation.", mention_author=False)
                    return
                if discord.utils.get(guild.forum_channels, name=name):
                    await message.reply("That forum already exists.", mention_author=False)
                    return
                created = await guild.create_forum(name, reason=reason)
            await message.reply(f"Created {created.mention}.", mention_author=False)
        elif action == "create_role":
            if not actor.guild_permissions.manage_roles or not me.guild_permissions.manage_roles:
                await message.reply("You and I both need Manage Roles permission.", mention_author=False)
                return
            if discord.utils.get(guild.roles, name=name):
                await message.reply("That role already exists.", mention_author=False)
                return
            role = await guild.create_role(name=name, mentionable=False, reason=reason)
            await message.reply(f"Created role **{discord.utils.escape_markdown(role.name)}**.", mention_author=False)
        elif action == "create_thread":
            if not isinstance(message.channel, discord.TextChannel):
                await message.reply("Ask me to start the thread in a regular text channel.", mention_author=False)
                return
            if not actor.guild_permissions.create_public_threads or not me.guild_permissions.create_public_threads:
                await message.reply("You and I both need Create Public Threads permission.", mention_author=False)
                return
            thread = await message.channel.create_thread(name=name, message=message, reason=reason)
            await message.reply(f"Started {thread.mention}.", mention_author=False)
    except discord.Forbidden:
        await message.reply("Discord denied the action; check permissions and role positions.", mention_author=False)
    except discord.HTTPException as exc:
        print(f"Discord API error: {exc}")
        await message.reply("Discord couldn't complete that action. Please try again.", mention_author=False)

@bot.tree.command(name="ping", description="Check whether the bot is responsive.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 ({round(bot.latency * 1000)} ms)")

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing.")
    bot.run(TOKEN)
