import os
import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

connection = sqlite3.connect("database/OreBot.db")
cursor = connection.cursor()

# Loads the secret token from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
SERVER_ID = int(os.getenv("GUILD_ID"))

BASE_RATE = 0.5
OFFLINE_CAP = 28800  # 8 hours in seconds

UPGRADES = {
    "pickaxe": {
        "rate_per_level": 0.2,
        "base_cost": 25,
        "cost_growth": 1.15,
        "tiers": [
            (0, "Copper pickaxe"),
            (6, "Iron pickaxe"),
            (16, "Steel pickaxe"),
            (31, "Diamond pickaxe"),
        ],
    },
    "cart": {
        "rate_per_level": 1.0,
        "base_cost": 300,
        "cost_growth": 1.15,
        "tiers": [
            (0, "Wooden cart"),
            (6, "Reinforced cart"),
            (16, "Powered cart"),
            (31, "Maglev cart"),
        ],
    },
    "drone": {
        "rate_per_level": 4.0,
        "base_cost": 2500,
        "cost_growth": 1.15,
        "tiers": [
            (0, "Scout drone"),
            (6, "Survey drone"),
            (16, "Industrial drone"),
            (31, "Drone swarm"),
        ],
    },
}


async def get_rate(user_id):
    result = cursor.execute(
        "SELECT upgrade_id, level FROM player_upgrades WHERE user_id = ?", [user_id]
    )
    player_upgrades = result.fetchall()
    rate = BASE_RATE
    for upgrade_id, level in player_upgrades:
        if upgrade_id in UPGRADES:
            rate_per_level = UPGRADES[upgrade_id]["rate_per_level"]
            upgrade_rate = rate_per_level * level
            rate += upgrade_rate
    return rate


async def get_shop(user_id):
    await collect(user_id)
    return_player_ore = cursor.execute(
        "SELECT ore FROM players WHERE user_id = ?", [user_id]
    )
    row = return_player_ore.fetchone()
    ore = row[0]

    result = cursor.execute(
        "SELECT upgrade_id, level FROM player_upgrades WHERE user_id = ?", [user_id]
    )
    player_upgrades = result.fetchall()
    owned = dict(player_upgrades)

    rows = []
    for upgrade_id in UPGRADES:
        level = owned.get(upgrade_id, 0)
        cost = upgrade_cost(upgrade_id, level)
        name = display_name(upgrade_id, level)
        row_dict = {
            "upgrade_id": upgrade_id,
            "display_name": name,
            "level": level,
            "cost": cost,
        }
        rows.append(row_dict)
    return (ore, rows)


async def get_or_create_player(user_id):
    result = cursor.execute("SELECT * FROM players WHERE user_id = ?", [user_id])
    players = result.fetchone()
    if players is None:
        last_collected = created_at = time.time()

        data = [user_id, last_collected, created_at]
        cursor.execute(
            "INSERT INTO players (user_id, last_collected, created_at) VALUES (?, ?, ?)",
            data,
        )
        connection.commit()

        result = cursor.execute("SELECT * FROM players WHERE user_id = ?", [user_id])
        players = result.fetchone()
        return players
    else:
        return players


async def get_leaderboard():
    """Ranks on lifetime_ore so spending doesn't lower your position.
    Doesn't collect first: that would mean a write per player on every
    call, so the numbers here lag until each player's next collect."""
    result = cursor.execute(
        "SELECT user_id, lifetime_ore FROM players ORDER BY lifetime_ore DESC LIMIT 10"
    )
    players = result.fetchall()
    return players


async def get_stats(user_id):
    gained = await collect(user_id)
    rate = await get_rate(user_id)

    get_ore = cursor.execute("SELECT ore FROM players WHERE user_id = ?", [user_id])
    player_ore = get_ore.fetchone()
    ore = player_ore[0]

    get_levels = cursor.execute(
        "SELECT upgrade_id, level FROM player_upgrades WHERE user_id = ?", [user_id]
    )
    player_level = get_levels.fetchall()

    players_info_dict = {
        "gained": gained,
        "rate": rate,
        "ore": ore,
        "upgrades": player_level,
    }
    return players_info_dict


async def collect(user_id):
    player = await get_or_create_player(user_id)
    ore = player[1]
    lifetime_ore = player[2]
    last_collected = player[3]

    player_upgrades_rate = await get_rate(user_id)

    now = time.time()
    elapsed = min(now - last_collected, OFFLINE_CAP)
    gained = elapsed * player_upgrades_rate

    ore += gained
    lifetime_ore += gained

    data = [ore, lifetime_ore, now, user_id]
    cursor.execute(
        "UPDATE players SET ore=?, lifetime_ore=?, last_collected=? WHERE user_id=?",
        data,
    )
    connection.commit()
    return gained


def upgrade_cost(upgrade_id, level):
    base_cost = UPGRADES[upgrade_id]["base_cost"]
    cost_growth = UPGRADES[upgrade_id]["cost_growth"]
    total = base_cost * cost_growth**level
    return int(total)


def display_name(upgrade_id, level):
    """Returns the tier name for this upgrade at this level.
    Walks the tier list in ascending order; the last match wins."""
    name = None
    for min_level, tier_name in UPGRADES[upgrade_id]["tiers"]:
        if level >= min_level:
            name = tier_name
    return name


async def buy(user_id, upgrade_id):
    if upgrade_id not in UPGRADES:
        return (False, None, None, None)  # upgrade_id doesn't exist
    await collect(user_id)
    return_player_ore = cursor.execute(
        "SELECT ore FROM players WHERE user_id = ?", [user_id]
    )
    row = return_player_ore.fetchone()
    ore = row[0]

    result = cursor.execute(
        "SELECT level FROM player_upgrades WHERE user_id = ? AND upgrade_id = ?",
        [user_id, upgrade_id],
    )
    player_level = result.fetchone()

    if player_level is None:
        level = 0
        owns_it = False
    else:
        level = player_level[0]
        owns_it = True
    cost = upgrade_cost(upgrade_id, level)

    if ore >= cost:
        ore = ore - cost
        level += 1
        if owns_it:
            cursor.execute(
                "UPDATE player_upgrades SET level = ? WHERE user_id=? AND upgrade_id=?",
                [level, user_id, upgrade_id],
            )
        else:
            cursor.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id, level) VALUES (?, ?, ?)",
                [user_id, upgrade_id, level],
            )
        cursor.execute("UPDATE players SET ore=? WHERE user_id=?", [ore, user_id])
        connection.commit()
        return (True, cost, ore, level)  # Bought upgrade
    else:
        return (False, cost, ore, level)  # Can't afford


async def upgrade_autocomplete(interaction: discord.Interaction, current: str):
    result = cursor.execute(
        "SELECT upgrade_id, level FROM player_upgrades WHERE user_id = ?",
        [interaction.user.id],
    )
    owned = dict(result.fetchall())

    choices = []
    for upgrade_id in UPGRADES:
        level = owned.get(upgrade_id, 0)
        name = display_name(upgrade_id, level)
        label = f"{name} (Lv {level})"
        if current.lower() in label.lower():
            choices.append(app_commands.Choice(name=label, value=upgrade_id))
    return choices


class Client(commands.Bot):
    async def on_ready(self):
        print(f"Logged on as {self.user}!")
        try:
            guild = discord.Object(id=SERVER_ID)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} commands to guild {guild.id}")

        except Exception as e:
            print(f"Error syncing commands: {e}")


intents = discord.Intents.default()
client = Client(command_prefix="!", intents=intents, help_command=None)
GUILD_ID = discord.Object(id=SERVER_ID)


@client.tree.command(
    name="mine", description="Collect the ore you've accumulated", guild=GUILD_ID
)
async def mine(interaction: discord.Interaction):
    gained = await collect(interaction.user.id)
    await interaction.response.send_message(f"You mined {gained:,.0f} ore.")


@client.tree.command(
    name="buy", description="Buy a pickaxe, cart, or drone.", guild=GUILD_ID
)
@app_commands.autocomplete(upgrade=upgrade_autocomplete)
async def buy_command(interaction: discord.Interaction, upgrade: str):
    success, cost, ore, level = await buy(interaction.user.id, upgrade)
    if success:
        message = f"Bought {display_name(upgrade, level)} for {cost:,.0f} ore (Lv {level}). You have {ore:,.0f} ore left."
    elif cost is None:
        message = f"There's no upgrade called '{upgrade}'."
    else:
        message = f"You need {cost:,.0f} ore, you have {ore:,.0f}."
    await interaction.response.send_message(message)


@client.tree.command(name="top", description="See the top 10 miners", guild=GUILD_ID)
async def leaderboard(interaction: discord.Interaction):
    lines = []
    players = await get_leaderboard()
    if not players:
        await interaction.response.send_message("Nobody's mined yet")
    else:
        for rank, (user_id, lifetime_ore) in enumerate(players, start=1):
            lines.append(f"{rank}. <@{user_id}> {lifetime_ore:,.0f} ore")
        await interaction.response.send_message(
            "\n".join(lines), allowed_mentions=discord.AllowedMentions.none()
        )


@client.tree.command(name="shop", description="Browse upgrades", guild=GUILD_ID)
async def shopping(interaction: discord.Interaction):
    ore, rows = await get_shop(interaction.user.id)

    embed = discord.Embed(
        title="🛒 Shop",
        description=f"You have **{ore:,.0f}** ore",
        color=discord.Color.dark_green(),
    )

    for row in rows:
        upgrade_id = row["upgrade_id"]
        level = row["level"]
        cost = row["cost"]

        rate_per_level = UPGRADES[upgrade_id]["rate_per_level"] * 60
        current_rate = rate_per_level * level
        next_rate = rate_per_level * (level + 1)

        affordable = cost <= ore
        mark = "✅" if affordable else "❌"

        embed.add_field(
            name=f"{mark} {row['display_name']} — Lv {level}",
            value=(
                f"Cost: **{cost:,}** ore\n"
                f"+{current_rate:,.0f}/min → **+{next_rate:,.0f}/min**"
            ),
            inline=False,
        )

    embed.set_footer(text="/buy to purchase")
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="stats", description="View your mine", guild=GUILD_ID)
async def stats_command(interaction: discord.Interaction):
    stats = await get_stats(interaction.user.id)

    embed = discord.Embed(title="⛏️ Your mine", color=discord.Color.dark_green())

    embed.add_field(name="Ore", value=f"**{stats['ore']:,.0f}**", inline=True)
    embed.add_field(
        name="Rate", value=f"**{stats['rate'] * 60:,.0f}**/min", inline=True
    )

    if stats["gained"] >= 1:
        embed.add_field(
            name="\u200b",
            value=f"🌙 Collected **{stats['gained']:,.0f}** ore while you were away",
            inline=False,
        )

    lines = []
    for upgrade_id, level in stats["upgrades"]:
        if upgrade_id in UPGRADES:
            name = display_name(upgrade_id, level)
            rate = UPGRADES[upgrade_id]["rate_per_level"] * level * 60
            lines.append(f"`{level}x` {name} — +{rate:,.0f}/min")

    if not lines:
        lines.append("*Nothing yet — try `/shop`*")

    embed.add_field(name="Equipment", value="\n".join(lines), inline=False)

    embed.set_author(
        name=interaction.user.name, icon_url=interaction.user.display_avatar.url
    )
    embed.set_footer(text="/mine to collect · /shop to upgrade")

    await interaction.response.send_message(embed=embed)


client.run(TOKEN)
