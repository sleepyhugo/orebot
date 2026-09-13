# OreBot

A Discord idle mining game built with Python, discord.py, and SQLite.

Players accumulate ore in real time whether or not they're online, spend it on
upgrades that increase their rate, and compete on a server leaderboard.

## How it works

Ore isn't tracked by a background loop. Each player row stores a
`last_collected` timestamp, and when a command runs, the bot calculates how much
time has passed and pays out `elapsed × rate`.

That has two useful consequences: the bot can be offline for days without anyone
losing progress, and the cost of running it doesn't scale with the number of
players — there's no per-player tick, only work when someone types something.

Accumulation is capped at 8 hours so a month-long absence doesn't produce a meaningless payout.

Players are created automatically on their first command there's no registration step.

## Commands

| Command | Description |
|---|---|
| `/mine` | Collect accumulated ore |
| `/shop` | Browse upgrades with costs and rate gains |
| `/buy` | Purchase an upgrade |
| `/stats` | View your mine, rate, and equipment |
| `/top` | Server leaderboard |

## Design notes

**Upgrade definitions live in Python, not the database.** Rebalancing is a
one-line edit to a dict rather than a schema migration. The database only stores
which upgrades each player owns and at what level.

**Two ore columns.** `ore` is spendable; `lifetime_ore` only ever increases and
is what the leaderboard ranks on, so buying upgrades never costs you position.

**Ore is stored as a float.** Flooring on every collect would silently delete
fractional progress for players with low rates.

**Game logic returns data; commands format it.** `get_shop` hands back a list of
dicts and the command decides whether that becomes plain text or an embed.

## Running it

Requires Python 3.12+ and a Discord bot application.

```bash
git clone https://github.com/sleepyhugo/orebot
cd orebot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create the database:

```bash
mkdir database
sqlite3 database/OreBot.db < schema.sql
```

Copy `.env.example` to `.env` and fill in your bot token and server ID:

DISCORD_TOKEN=your_token_here
GUILD_ID=your_server_id_here


The bot needs these permissions: View Channels, Send Messages, Embed Links,
Read Message History, Use Slash Commands. Scopes: `bot` and
`applications.commands`.

```bash
python OreBot.py
```

## Known limitations

- No maximum level on upgrades
- Concurrent commands from the same player could double-pay; needs a per-user lock or a synchronous read-compute-write
- Ore and level queries are duplicated across several functions
- Leaderboard numbers lag until each player's next collect
- Runs against a single SQLite file with no connection pooling