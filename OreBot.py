import os, time
import sqlite3

import discord
from discord.ext import commands
from discord import app_commands

from dotenv import load_dotenv

# discord_id = you discord id here

connection = sqlite3.connect("database/OreBot.db")
cursor = connection.cursor()

# Loads the secret token from the .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_ID = int(os.getenv('GUILD_ID'))

BASE_RATE = 0.5
OFFLINE_CAP = 28800 # 8 hours in seconds

UPGRADES = {
  "pickaxe": {
    "display_name": "Copper pickaxe",
    "rate_per_level": 0.2,
    "base_cost": 25,
    "cost_growth": 1.15
  },
  "cart": {
    "display_name": "Ore cart",
    "rate_per_level": 1.0,
    "base_cost": 300,
    "cost_growth": 1.15
  },
  "drone": {
    "display_name": "Mining drone",
    "rate_per_level": 4.0,
    "base_cost": 2500,
    "cost_growth": 1.15
  }
}

async def get_rate(user_id):
  result = cursor.execute("SELECT upgrade_id, level FROM player_upgrades WHERE user_id = ?", [user_id])
  player_upgrades = result.fetchall()
  rate = BASE_RATE
  for upgrade_id, level in player_upgrades:
    if upgrade_id in UPGRADES:
      rate_per_level = UPGRADES[upgrade_id]["rate_per_level"]
      upgrade_rate = rate_per_level * level
      rate += upgrade_rate
  return rate

async def get_or_create_player(user_id):
  result = cursor.execute("SELECT * FROM players WHERE user_id = ?", [user_id])
  players = result.fetchone()
  if players is None:
    last_collected = created_at = time.time()

    data = [user_id, last_collected, created_at]
    cursor.execute("INSERT INTO players (user_id, last_collected, created_at) VALUES (?, ?, ?)", data)
    connection.commit()

    result = cursor.execute("SELECT * FROM players WHERE user_id = ?", [user_id])
    players = result.fetchone()
    return players
  else:
    print(f"User id: {user_id} is in players table already.\n")
    return players

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
  cursor.execute("UPDATE players SET ore=?, lifetime_ore=?, last_collected=? WHERE user_id=?", data)
  connection.commit()
  return gained

def upgrade_cost(upgrade_id, level):
  base_cost = UPGRADES[upgrade_id]["base_cost"]
  cost_growth = UPGRADES[upgrade_id]["cost_growth"]
  total = base_cost * cost_growth ** level
  return int(total)

async def buy(user_id, upgrade_id):
  if upgrade_id not in UPGRADES:
    return (False, None, None) # upgrade_id doesn exist
  gained = await collect(user_id)
  return_player_ore = cursor.execute("SELECT ore FROM players WHERE user_id = ?", [user_id])
  row = return_player_ore.fetchone()
  ore = row[0]

  result = cursor.execute("SELECT level FROM player_upgrades WHERE user_id = ? AND upgrade_id = ?", [user_id, upgrade_id])
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
      cursor.execute("UPDATE player_upgrades SET level = ? WHERE user_id=? AND upgrade_id=?", [level, user_id, upgrade_id])
    else:
      cursor.execute("INSERT INTO player_upgrades (user_id, upgrade_id, level) VALUES (?, ?, ?)", [user_id, upgrade_id, level])
    cursor.execute("UPDATE players SET ore=? WHERE user_id=?", [ore, user_id])
    connection.commit()
    return (True, cost, ore) # Bought upgrade
  else:
    return (False, cost, ore) # Can't afford

class Client(commands.Bot):

  async def on_ready(self):
    print(f"Logged on as {self.user}!")
    try:
      guild = discord.Object(id=SERVER_ID)
      synced = await self.tree.sync(guild=guild)
      print(f"Synced {len(synced)} commands to guild {guild.id}")

    except Exception as e:
      print(f"Error syncing commands: {e}")

  async def on_message(self, message):
    if message.author == self.user:
      return

    if message.content.startswith('hello'):
      await message.channel.send(f"Hi there {message.author}")

  async def on_reaction_add(self, reaction, user):
    await reaction.message.channel.send("You reacted")

intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix="!", intents=intents)

GUILD_ID = discord.Object(id=SERVER_ID)

@client.tree.command(name="mine", description="mining description", guild=GUILD_ID)
async def mine(interaction: discord.Interaction):
  gained = await collect(interaction.user.id)
  await interaction.response.send_message(f"You mined {gained:,.0f} ore.")

@client.tree.command(name="buy", description="Buy a pickaxe, cart, or drone.", guild=GUILD_ID)
async def buy_command(interaction: discord.Interaction, upgrade: str):
  success, cost, ore = await buy(interaction.user.id, upgrade)
  if success:
    message = f"Bought {upgrade} for {cost:,.0f} ore. You have {ore:,.0f} left."
  elif cost is None:
    message = f"There's no upgrade called '{upgrade}'."
  else:
    message = f"You need {cost:,.0f} ore, you have {ore:,.0f}."
  await interaction.response.send_message(message)

# Embed not done yet
@client.tree.command(name="embed", description="Embed demo!", guild=GUILD_ID)
async def printer(interaction: discord.Interaction):
  embed = discord.Embed(title="Mine", description="Depth 1 - Copper", color=discord.Color.dark_green())
  embed.add_field(name="Ore", value="ore amount will go here", inline=True)
  embed.add_field(name="Rate", value="time in mins go here /min", inline=True)
  embed.add_field(name="While away", value="ore amount", inline=False)
  embed.set_author(name=interaction.user.name, url="https://github.com/sleepyhugo", icon_url="https://i.etsystatic.com/57565963/r/il/c9ac96/6835519393/il_fullxfull.6835519393_rn0l.jpg")
  embed.set_footer(text="This is the footer!")
  await interaction.response.send_message(embed=embed)

client.run(TOKEN)