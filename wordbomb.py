import asyncio
import datetime
import random
import time

import discord
from discord.ext import commands, tasks
from tinydb import TinyDB, Query

intents = discord.Intents.default()
intents.message_content = True
bot = commands.AutoShardedBot(intents=intents, command_prefix="None")

db = TinyDB('db.json')

update_time = 0
on_ready_debounce = False
game_started: list[int] = []
generated: dict[int, str] = {}
banned: dict[int, set[str]] = {}
current_player: dict[int, int] = {}
correct: dict[int, bool] = {}
player_list: dict[int, dict[int, int]] = {}
singleplayer: dict[int, bool] = {}
rounds: dict[int, int] = {}
winner_found: dict[int, bool] = {}

inputs = ['TRO', 'JET', 'STR', 'ADJ', 'CRA', 'ISE', 'TIC', 'INT', 'MIN', 'SCA', 'INC', 'VER', 'RED', 'TRA', 'MEN', 'KIL', 'ZAP', 'LUB', 'STA', 'REF', 'LIT', 'IST', 'MIS', 'ANG', 'REV', 'LAT', 'DIS', 'BLA', 'SYR', 'DIG', 'CAT', 'INE', 'LIN', 'RAF', 'PER', 'SAV', 'ROA', 'SCH', 'LOV', 'SOF', 'CON', 'HUN', 'LAG', 'COM', 'ICA', 'INS', 'RIS', 'GAG', 'INO', 'LOW', 'RAT', 'WOR', 'BRE', 'LOG', 'ORI', 'HAN', 'ATT', 'TIN', 'DRA', 'UNP', 'PUR', 'PAL', 'MIL', 'FOR', 'GRA', 'ATE', 'PAT', 'BER', 'BET', 'WEA', 'IOD', 'RES', 'TRI', 'BRO', 'RAN', 'PRO', 'WHI', 'FLA', 'ELL', 'ENT', 'INK', 'ABS', 'CLA', 'CAL', 'OVE', 'IMI', 'ILL', 'COK', 'SHI', 'SAT', 'CRO', 'DEP', 'STI', 'MAT', 'SIN', 'IDE', 'SPL']

with open("wordlist.txt", 'r') as file:
    words = {line.strip() for line in file}

@bot.event
async def on_ready():
    global on_ready_debounce
    if on_ready_debounce:
        return
    on_ready_debounce = True
    print(f"Logged in as {bot.user}")
    _ = await bot.tree.sync()
    now = datetime.datetime.now()
    minutes_until_next_half_hour = (30 - now.minute % 30) % 30
    seconds_until_next_half_hour = minutes_until_next_half_hour * 60 - now.second
    await discord.utils.sleep_until(now + datetime.timedelta(seconds=seconds_until_next_half_hour))
    hourly_task.start()

@tasks.loop(minutes=30)
async def hourly_task():
    for item in db:
        bot.loop.create_task(start_game(bot.get_channel(item['channel']), item['lifes'], item['seconds'], item['lock'], item['msg']))  # pyright: ignore

@bot.event
async def on_message(message: discord.Message):
    global update_time, game_started, current_player, words, correct, banned, generated
    if update_time + 300 < time.time():
        update_time = time.time()
        await bot.change_presence(
            activity=discord.CustomActivity(name=f"Playing with bombs in {len(bot.guilds):,} servers")
        )

    text = message.content.lower()

    if generated.get(message.channel.id, False) and text in words and message.channel.id in game_started and generated[message.channel.id].lower() in text:
        if message.author.id == current_player[message.channel.id] and text not in banned[message.channel.id] and not correct[message.channel.id]:
            correct[message.channel.id] = True
            banned[message.channel.id].add(text)
            await message.add_reaction("✅")
        elif text in banned[message.channel.id]:
            await message.add_reaction("🟡")
        else:
            await message.add_reaction("☑")


@bot.tree.command(description="Schedule a hourly game of bomb party in this channel! (requres Manage Channels)")
@discord.app_commands.default_permissions(manage_channels=True)
@discord.app_commands.describe(lifes="Amount of lives every player has (default: 3)",
                               seconds="Amount of seconds between each round (default: 8)",
                               lock="Whether to lock the channel when a game is not happening (default: False)",
                               msg="A custom message for the game start. Use for pings etc (default: None)")
async def schedule(message: discord.Interaction, lifes: int | None, seconds: int | None, lock: bool | None, msg: str | None):
    _lifes: int = lifes if lifes else 3
    _seconds: float = seconds if seconds else 8
    _lock: bool = lock if lock is not None else False
    _msg: str = msg if msg else "This is a scheduled game!"
    if not message.channel or not isinstance(message.channel, discord.TextChannel):
        await message.response.send_message("This command can only be used in a text channel", ephemeral=True)
        return
    _ = db.insert({'channel': message.channel.id, 'lifes': _lifes, 'seconds': _seconds, 'lock': _lock, 'msg': _msg})
    await message.response.send_message("Channel added! A game with those settings will happen every 30 minutes.")


@bot.tree.command(description="Remove a scheduled game of bomb party in this channel (requres Manage Channels)")
@discord.app_commands.default_permissions(manage_channels=True)
async def unschedule(message: discord.Interaction):
    if not message.channel or isinstance(message.channel, discord.ForumChannel) or isinstance(message.channel, discord.CategoryChannel):
        await message.response.send_message("This command can only be used in a text channel", ephemeral=True)
        return
    db.remove(Query().channel==message.channel.id)
    await message.response.send_message("Channel removed!")

@bot.tree.command()
async def privacy(interaction):
    await interaction.response.send_message("https://catbot.minkos.lol/pp", ephemeral=True)

@bot.tree.command(description="Start a game of bomb party! (requres Manage Channels)")
@discord.app_commands.default_permissions(manage_channels=True)
@discord.app_commands.describe(lifes="Amount of lives every player has (default: 3)", seconds="Amount of seconds between each round (default: 8)")
async def play(message: discord.Interaction, lifes: int | None, seconds: int | None):
    _lifes: int = lifes if lifes else 3
    _seconds: float = seconds if seconds else 8
    if not message.channel or (not isinstance(message.channel, discord.TextChannel) and not isinstance(message.channel, discord.Thread)):
        await message.response.send_message("This command can only be used in a text channel", ephemeral=True)
        return
    if message.channel.id not in game_started:
        _ = await message.response.send_message("Starting game...", ephemeral=True)
        await start_game(message.channel, _lifes, _seconds)
    else:
        _ = await message.response.send_message("Game is already in progress!", ephemeral=True)

async def start_game(channel: discord.TextChannel | discord.Thread, _lifes: int, _seconds: float, lock: bool = False, msg: str = ""):
    if channel.id in game_started:
        return
    game_started.append(channel.id)

    player_list[channel.id] = {}
    collecting = True

    async def collect(interaction: discord.Interaction):
        if not collecting:
            await interaction.response.send_message("Game is already in progress!", ephemeral=True)
            return
        if not channel:
            return
        if interaction.user.id not in player_list[channel.id]:
            player_list[channel.id][interaction.user.id] = _lifes
            await interaction.response.send_message("You joined the game!", ephemeral=True)
        else:
            del player_list[channel.id][interaction.user.id]
            await interaction.response.send_message("You left the game!", ephemeral=True)

    view = discord.ui.View(timeout=3600)
    button = discord.ui.Button(label="Join", style=discord.ButtonStyle.blurple)
    button.callback = collect
    _ = view.add_item(button)
    wait_time = 30 if not msg else 60
    await channel.send(
        f"{msg}\nClick the button to join! The game will start in {wait_time} seconds.\nSettings: {_lifes} lifes, {_seconds} seconds\n\n✅ Correct\n☑ Correct, not your turn\n🟡 Already used", view=view
    )
    await asyncio.sleep(wait_time)
    collecting = False

    _ = await channel.send(f"Game staring! {len(player_list[channel.id])} players joined...")
    if lock and isinstance(channel, discord.TextChannel):
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)
    await asyncio.sleep(3)

    singleplayer[channel.id] = False
    if len(player_list[channel.id]) == 1:
        _ = await channel.send("Only one player reacted. Starting a singleplayer game...")
        await asyncio.sleep(3)
        singleplayer[channel.id] = True

    if len(player_list[channel.id]) >= 1:
        winner_found[channel.id] = False
        banned[channel.id] = set()
        rounds[channel.id] = 0

        while not winner_found[channel.id]:
            rounds[channel.id] += 1
            temp_list = list(player_list[channel.id].items())
            random.shuffle(temp_list)
            player_list[channel.id] = dict(temp_list)
            for user, lifes in player_list[channel.id].items():
                if lifes == 0 or winner_found[channel.id]:
                    continue

                current_player[channel.id] = user
                correct[channel.id] = False

                generated[channel.id] = random.choice(inputs)

                _ = await channel.send(
                    f"<@{user}>, type a word containing: **{generated[channel.id].upper()}**"
                )

                await asyncio.sleep(_seconds)

                current_player[channel.id] = 0

                if not correct[channel.id]:
                    lifes = lifes - 1
                    _ = await channel.send(
                        f"Time's up! -1 HP ({lifes} remaining)"
                    )
                    player_list[channel.id][user] = lifes

                    if lifes == 0:
                        _ = await channel.send(f"<@{user}> is eliminated!")
                        count = 0
                        if not singleplayer[channel.id]:
                            for lifes in player_list[channel.id].values():
                                if lifes != 0:
                                    count += 1
                            if count <= 1:
                                winner_found[channel.id] = True
                                break
                        else:
                            winner_found[channel.id] = True

                await asyncio.sleep(2)

            if not winner_found[channel.id] and not singleplayer[channel.id]:
                leaderboard = ""
                sorted_lb = {
                    k: v
                    for k, v in sorted(
                        player_list[channel.id].items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                }

                for player, lifes in sorted_lb.items():
                    user = await bot.fetch_user(player)
                    leaderboard = leaderboard + f"{lifes} - {user.name}\n"
                _ = await channel.send(
                    f"**Round {rounds[channel.id]}**\n```\nCurrent lives remaining:\n{leaderboard}```"
                )
                await asyncio.sleep(2)

            if not winner_found[channel.id] and rounds[channel.id] >= 10:
                _seconds -= 0.5
                _ = await channel.send(f"**SUDDEN DEATH**\nTime to answer got decreased by 0.5 seconds to **{_seconds}**!")
                await asyncio.sleep(3)

        if not singleplayer[channel.id]:
            for user, lifes in player_list[channel.id].items():
                if lifes != 0:
                    _ = await channel.send(f"<@{user}> wins! The game lasted {rounds[channel.id]} rounds.")
        else:
            _ = await channel.send(f"GG! The game lasted {rounds[channel.id]} rounds.")
    else:
        _ = await channel.send("Not enough players to play.")
    game_started.remove(channel.id)
    await asyncio.sleep(5)
    if lock and isinstance(channel, discord.TextChannel):
        overwrite = channel.overwrites_for(channel.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)


bot.run("your token goes here")
