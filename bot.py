import os
from pathlib import Path

import discord
from discord import app_commands

from intent_parser import extract_intents

TOKEN = os.getenv("DISCORD_TOKEN")
READY_FILE = os.getenv("BOT_READY_FILE")


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

    actions = extract_intents(message.content)
    if not actions:
        await message.reply(
            "I can create text channels, forum channels, threads, and roles, "
            "and make a post in a forum. Please name the items and describe the post.",
            mention_author=False,
        )
        return

    guild = message.guild
    actor = message.author if isinstance(message.author, discord.Member) else None
    me = guild.me
    if not actor or not me:
        return

    reason = f"Requested by {actor} via SllBot"
    created_forums = {}

    try:
        for action_data in actions:
            action, name = action_data[0], action_data[1]

            if action in ("create_text_channel", "create_forum"):
                if not actor.guild_permissions.manage_channels or not me.guild_permissions.manage_channels:
                    await message.reply("You and I both need Manage Channels permission.", mention_author=False)
                    return

                if action == "create_text_channel":
                    if discord.utils.get(guild.text_channels, name=name):
                        await message.reply(f"The text channel **{discord.utils.escape_markdown(name)}** already exists.", mention_author=False)
                        return
                    created = await guild.create_text_channel(name, reason=reason)
                    await message.reply(f"Created {created.mention}.", mention_author=False)
                    continue

                existing = discord.utils.get(guild.forum_channels, name=name)
                post_requested = any(
                    item[0] == "create_forum_post" and item[1] == name
                    for item in actions
                )
                if existing:
                    if not post_requested:
                        await message.reply(f"The forum **{discord.utils.escape_markdown(name)}** already exists.", mention_author=False)
                        return
                    created_forums[name] = existing
                    await message.reply(f"That forum already exists; I'll use {existing.mention} for the post.", mention_author=False)
                    continue

                if not hasattr(guild, "create_forum"):
                    await message.reply("Please update discord.py to enable forum creation.", mention_author=False)
                    return
                created = await guild.create_forum(name, reason=reason)
                created_forums[name] = created
                await message.reply(f"Created {created.mention}.", mention_author=False)

            elif action == "create_forum_post":
                forum_name, title, body = action_data[1], action_data[2], action_data[3]
                forum = created_forums.get(forum_name) or discord.utils.get(guild.forum_channels, name=forum_name)
                if forum is None:
                    await message.reply(
                        f"I couldn't find the forum **{discord.utils.escape_markdown(forum_name)}** to post in.",
                        mention_author=False,
                    )
                    return

                actor_perms = forum.permissions_for(actor)
                bot_perms = forum.permissions_for(me)
                if not actor_perms.send_messages or not actor_perms.create_public_threads:
                    await message.reply("You need permission to send messages and create posts in that forum.", mention_author=False)
                    return
                if not bot_perms.send_messages or not bot_perms.create_public_threads:
                    await message.reply("I need permission to send messages and create posts in that forum.", mention_author=False)
                    return

                thread, _starter_message = await forum.create_thread(
                    name=title,
                    content=body,
                    reason=reason,
                )
                await message.reply(f"Created the post [{discord.utils.escape_markdown(title)}]({thread.jump_url}) in {forum.mention}.", mention_author=False)

            elif action == "create_role":
                if not actor.guild_permissions.manage_roles or not me.guild_permissions.manage_roles:
                    await message.reply("You and I both need Manage Roles permission.", mention_author=False)
                    return
                if discord.utils.get(guild.roles, name=name):
                    await message.reply(f"The role **{discord.utils.escape_markdown(name)}** already exists.", mention_author=False)
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
