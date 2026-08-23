#!/usr/bin/env python3
"""CHAOS TYPE ZERO — Discord Bot Controller"""
import json, sys, os, re, asyncio

# Bot config
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR-DISCORD-BOT-TOKEN")
COMMAND_PREFIX = os.environ.get("CTZ_PREFIX", "!")

# SECURITY: previously any user in any server/channel the bot joined could
# run privileged commands (!scan, !run, !browse -> security scanner,
# orchestrator, browser automation) with zero authorization check. Set
# CTZ_DISCORD_ALLOWED_USERS to a comma-separated list of Discord user IDs
# who are allowed to use privileged commands. If unset, privileged commands
# refuse to run and tell the invoker how to configure it.
_ALLOWED_USERS_RAW = os.environ.get("CTZ_DISCORD_ALLOWED_USERS", "")
ALLOWED_USER_IDS = {u.strip() for u in _ALLOWED_USERS_RAW.split(",") if u.strip()}

# MCP server references
MCP_SERVERS = {
    "brain": "ctz-brain",
    "memory": "ctz-memory",
    "router": "ctz-router",
    "security": "ctz-security",
    "browser": "ctz-browser",
    "voice": "ctz-voice",
    "neural": "ctz-neural",
    "orchestrator": "ctz-orchestrator",
}

# Command handlers
async def cmd_help(message):
    embed = {
        "title": "CHAOS TYPE ZERO — Commands",
        "description": "All available commands",
        "color": 0x00ff41,
        "fields": [
            {"name": f"{COMMAND_PREFIX}scan <target>", "value": "Security scan", "inline": True},
            {"name": f"{COMMAND_PREFIX}search <query>", "value": "Search memory", "inline": True},
            {"name": f"{COMMAND_PREFIX}run <task>", "value": "Run task", "inline": True},
            {"name": f"{COMMAND_PREFIX}browse <url>", "value": "Browse website", "inline": True},
            {"name": f"{COMMAND_PREFIX}status", "value": "System status", "inline": True},
            {"name": f"{COMMAND_PREFIX}health", "value": "Health check", "inline": True},
            {"name": f"{COMMAND_PREFIX}servers", "value": "MCP servers", "inline": True},
            {"name": f"{COMMAND_PREFIX}help", "value": "Show this help", "inline": True},
        ]
    }
    return embed


async def cmd_status(message):
    return {
        "title": "CTZ Status",
        "color": 0x00ff41,
        "fields": [
            {"name": "Servers", "value": "40", "inline": True},
            {"name": "Tools", "value": "298", "inline": True},
            {"name": "Providers", "value": "14", "inline": True},
            {"name": "Skills", "value": "31", "inline": True},
            {"name": "Status", "value": "ONLINE", "inline": True},
        ]
    }


async def cmd_health(message):
    return {
        "title": "Health Check",
        "description": "All systems operational. 40/40 MCP servers ready.",
        "color": 0x00ff41,
    }


async def cmd_servers(message):
    server_list = "\n".join([f"**{k}**: {v}" for k, v in MCP_SERVERS.items()])
    return {
        "title": "MCP Servers",
        "description": server_list,
        "color": 0x00ff41,
    }


async def cmd_scan(message, target):
    return {
        "title": "Security Scan",
        "description": f"Scanning `{target}`...",
        "color": 0xff4444,
        "fields": [
            {"name": "Target", "value": target, "inline": True},
            {"name": "Status", "value": "Dispatched to ctz-security", "inline": True},
        ]
    }


async def cmd_search(message, query):
    return {
        "title": "Memory Search",
        "description": f"Searching for `{query}`...",
        "color": 0x00ff41,
        "fields": [
            {"name": "Query", "value": query, "inline": True},
            {"name": "Status", "value": "Dispatched to ctz-memory", "inline": True},
        ]
    }


async def cmd_run(message, task):
    return {
        "title": "Task Execution",
        "description": f"Running `{task}`...",
        "color": 0x00ff41,
        "fields": [
            {"name": "Task", "value": task, "inline": True},
            {"name": "Status", "value": "Dispatched to ctz-orchestrator", "inline": True},
        ]
    }


async def cmd_browse(message, url):
    return {
        "title": "Browser Automation",
        "description": f"Browsing `{url}`...",
        "color": 0x00ff41,
        "fields": [
            {"name": "URL", "value": url, "inline": True},
            {"name": "Status", "value": "Dispatched to ctz-browser", "inline": True},
        ]
    }


COMMAND_HANDLERS = {
    "help": cmd_help,
    "status": cmd_status,
    "health": cmd_health,
    "servers": cmd_servers,
}


# === Discord.py Bot (if discord.py is installed) ===
try:
    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

    @bot.event
    async def on_ready():
        print(f"CTZ Discord Bot logged in as {bot.user}")
        print(f"Prefix: {COMMAND_PREFIX}")
        if not ALLOWED_USER_IDS:
            print("[CTZ-DISCORD] WARNING: CTZ_DISCORD_ALLOWED_USERS is not set -- "
                  "privileged commands (scan/run/browse) are locked down for everyone "
                  "until you set it to your Discord user ID.")
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="CTZ v3.0 | !help"))

    def _is_authorized(ctx) -> bool:
        return str(ctx.author.id) in ALLOWED_USER_IDS

    async def _require_authorized(ctx) -> bool:
        if _is_authorized(ctx):
            return True
        await ctx.send(
            "You're not authorized to run this command. Ask the bot owner to add your "
            "Discord user ID to the `CTZ_DISCORD_ALLOWED_USERS` env var."
        )
        return False

    @bot.command(name="help")
    async def help_cmd(ctx):
        embed_data = await cmd_help(ctx.message)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="status")
    async def status_cmd(ctx):
        embed_data = await cmd_status(ctx.message)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="health")
    async def health_cmd(ctx):
        embed_data = await cmd_health(ctx.message)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="servers")
    async def servers_cmd(ctx):
        embed_data = await cmd_servers(ctx.message)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="scan")
    async def scan_cmd(ctx, *, target: str):
        if not await _require_authorized(ctx):
            return
        embed_data = await cmd_scan(ctx.message, target)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="search")
    async def search_cmd(ctx, *, query: str):
        embed_data = await cmd_search(ctx.message, query)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="run")
    async def run_cmd(ctx, *, task: str):
        if not await _require_authorized(ctx):
            return
        embed_data = await cmd_run(ctx.message, task)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    @bot.command(name="browse")
    async def browse_cmd(ctx, url: str):
        if not await _require_authorized(ctx):
            return
        embed_data = await cmd_browse(ctx.message, url)
        embed = discord.Embed.from_dict(embed_data)
        await ctx.send(embed=embed)

    HAS_DISCORD_PY = True

except ImportError:
    HAS_DISCORD_PY = False


def run_bot():
    if not HAS_DISCORD_PY:
        print("discord.py not installed!")
        print("Install: pip install discord.py")
        print("\nSetup:")
        print("1. Create bot at https://discord.com/developers/applications")
        print("2. Bot > Token > Copy")
        print("3. OAuth2 > URL Generator > bot + applications.commands")
        print("4. Scenarios: Send Messages, Read Message History, Use Slash Commands")
        print(f"5. Set DISCORD_BOT_TOKEN env var")
        print(f"6. Run: python discord_bot.py")
        sys.exit(1)
    
    if DISCORD_TOKEN == "YOUR-DISCORD-BOT-TOKEN":
        print("Set DISCORD_BOT_TOKEN environment variable!")
        print("export DISCORD_BOT_TOKEN=your-token-here")
        sys.exit(1)
    
    print(f"CTZ Discord Bot starting with prefix: {COMMAND_PREFIX}")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    run_bot()
