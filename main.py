import asyncio
import json
import os
import random
import re
import string
import sys
import threading
import time

import discord

import requests
from discord.ext import tasks

try:
    import Image
except ImportError:
    from PIL import Image

from collections import namedtuple
from datetime import datetime
from loguru import logger
from lib import solver


class CountUtils:
    def __init__(self):
        self.integer = 0

    def update(self):
        self.integer += 1

    def get(self):
        return self.integer

    def reset(self):
        self.integer = 0


class TimerUtils:
    def __init__(self):
        self.ms = self.get_current_ms()

    def has_reached(self, milliseconds):
        return self.get_current_ms() - self.ms > milliseconds

    def reset(self):
        self.ms = self.get_current_ms()

    @staticmethod
    def get_current_ms():
        return int(round(time.time() * 1000))


class LoggerSetup:
    FILE_LOG_FORMAT = ("<white>{time:YYYY-MM-DD HH:mm:ss}</white> | <level>{level: <8}</level> | <white>{"
                       "message}</white>")
    CONSOLE_LOG_FORMAT = "<white>{time:HH:mm:ss}</white> | <level>{level: <8}</level> | <white>{message}</white>"

    def __init__(self, debug: bool = True):
        logger.remove()
        log_file_name = f'{datetime.now().strftime("%d-%m-%Y")}.log'
        log_file_path = log_file_name
        logger.add(log_file_path, format=self.FILE_LOG_FORMAT, level="DEBUG", rotation='1 day')
        logger.add(sys.stderr, colorize=True, format=self.CONSOLE_LOG_FORMAT, level='DEBUG' if debug else 'INFO')


LoggerSetup()

if not os.path.exists("config.json"):
    default_config = {
        "bot": {
            "tokens": ["Bot tokens (currently only one supported)"],
            "prefix": "!"
        },
        "fish": {
            "bot_id": 574652751745777665,
            "channels": [
                626194399986188300, 626194640013361234,
                626194665271590912, 627721707125211137,
                627721733784469527, 776131741655892008,
                776131883796922388, 776131883796922388,
                776131912661205043, 776131926431760424,
                776131937927692308
            ],
            "channel_move_rate": [750, 1750],
            "sell_rate": [2000, 3560],
            "prestige_rate": [7500, 12000],
            "base_cooldown": 1000,
            "captcha_attempts": 3
        }
    }
    with open("config.json", "w+") as f:
        json.dump(default_config, f, ensure_ascii=False, indent=2)
    logger.error("Configuration doesn't found. Generated one for you.")
    sys.exit(0)

with open('config.json', 'r') as file:
    config = json.load(file)

BOT_TOKENS = config["bot"]["tokens"]
BOT_PREFIX = config["bot"]["prefix"]

FISH_BOT_ID = config["fish"]["bot_id"]
FISH_CHANNELS = config["fish"]["channels"]

MOVE_RATE = config["fish"]["channel_move_rate"]
SELL_RATE = config["fish"]["sell_rate"]
PRESTIGE_RATE = config["fish"]["prestige_rate"]

COOLDOWN = config["fish"]["base_cooldown"]
CAPTCHA_ATTEMPTS = config["fish"]["captcha_attempts"]

if len(SELL_RATE) > 2:
    logger.warning("Sell rate longer than two elements. In use only first two.")

if CAPTCHA_ATTEMPTS > 4:
    logger.error("Maximum value for captcha attempts is 4. (Fish bot limit)")
    sys.exit(-1)


def get_random_cooldown(cooldown: int) -> int:
    return cooldown + random.randrange(120, 1769)


async def perform_delayed_click(component):
    await asyncio.sleep(random.uniform(0.4, 1.65))
    await component.click()


def restart():
    os.execv(sys.executable, [os.path.basename(sys.executable)] + sys.argv)


class FishBot(discord.Client):
    def __init__(self):
        self.timer = TimerUtils()
        self.fish_counter = CountUtils()
        self.sell_counter = CountUtils()
        self.buy_counter = CountUtils()
        self.prestige_counter = CountUtils()

        self.running = True
        self.locked = False

        self.fish_commands = {}
        self.verify_commands = {}
        self.prestige_commands = {}

        self.fish_bot_id = FISH_BOT_ID
        self.channels = FISH_CHANNELS

        self.cooldown = COOLDOWN

        self.move_rate = MOVE_RATE
        self.sell_rate = SELL_RATE
        self.prestige_rate = PRESTIGE_RATE

        self.parsed_channels = []

        self.latest_fish: float = -1.0
        self.latest_captcha: float = -1.0

        self.level = -1
        self.captcha_attempts = CAPTCHA_ATTEMPTS  # +extra attempt when captcha appears first time
        self.captcha_attempt = 0

        self.current_channel = None

        super().__init__()

    @tasks.loop(minutes=5)
    async def check_activity(self):
        if self.latest_fish != -1.0:
            diff = (time.time() - self.latest_fish) / 60
            if diff > 5:
                logger.warning("Restarting script due to inactivity")
                restart()

    async def on_resumed(self):
        self.locked = True
        logger.warning("Session resumed. Restarting bot to avoid errors...")
        restart()

    async def on_ready(self):
        self.locked = True
        logger.success(f'Logged on as {self.user}')
        self.timer.reset()
        self.parsed_channels: list[discord.TextChannel] = []
        logger.info("Parsing channels...")
        for channel_id in self.channels:
            try:
                self.parsed_channels.append(await self.fetch_channel(channel_id))
            except discord.errors.DiscordException:
                logger.warning(f"Can't get channel with id: {channel_id}")
        if len(self.parsed_channels) == 0:
            logger.error("Can't parse any channels. Try change channels in config.yml, exiting...")
            sys.exit(-1)
        logger.info("Parsing commands in all channels...")
        for channel in self.parsed_channels:
            async for command in channel.slash_commands():
                if command.application_id == self.fish_bot_id:
                    guild_id = channel.guild.id
                    channel_id = channel.id

                    if guild_id not in self.fish_commands:
                        self.fish_commands[guild_id] = {}
                    if guild_id not in self.verify_commands:
                        self.verify_commands[guild_id] = {}
                    if guild_id not in self.prestige_commands:
                        self.prestige_commands[guild_id] = {}

                    if command.name == "fish":
                        self.fish_commands[guild_id][channel_id] = command
                    if command.name == "verify":
                        self.verify_commands[guild_id][channel_id] = command
                    if command.name == "prestige":
                        for child in command.children:
                            if child.name == "reset":
                                self.prestige_commands[guild_id][channel_id] = child

            await asyncio.sleep(random.uniform(2.75, 3.43))
        if len(self.fish_commands) == 0:
            logger.error("Can't find commands! Check if applications enabled.")
            sys.exit(-1)

        self.current_channel = random.choice(self.parsed_channels)
        logger.warning(f"Switched to {self.current_channel.name} in {self.current_channel.guild.name}")
        logger.info("Fetching info...")
        self.locked = False
        await self.check_activity.start()

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if self.running:
            if after.guild and after.embeds and after.author.id == self.fish_bot_id:
                if (any(embed.author and self.user.name in embed.author.name for embed in after.embeds) or
                        (after.interaction and after.interaction.user
                         and after.components and after.interaction.user == self.user) or
                        any(embed.title and self.user.name in embed.title for embed in after.embeds)):
                    await self.handle_embeds(after)

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            await self.handle_commands(message)
        if not self.current_channel:
            return
        if (not self.running or message.author.id != self.fish_bot_id
                or message.channel.id != self.current_channel.id):
            return
        if "You may now continue" in message.content:
            logger.success("Captcha solved.")
            await asyncio.sleep(random.uniform(1.12, 2.31))
            self.locked = False
            await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()
        if message.embeds:
            await self.handle_embeds(message)
        if "You must wait" in message.content:
            await self.handle_wait_time(message)
        if "Incorrect code" in message.content:
            await self.handle_incorrect_code()

    async def handle_commands(self, message: discord.Message):
        if message.content == f"{BOT_PREFIX}pause":
            self.running = not self.running
            if self.running:
                logger.info("Starting fishing...")
                await message.edit(content=f"FishBot enabled!")
                await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()
            else:
                logger.info("Bot stopped by user.")
                await message.edit(content=f"FishBot disabled!")
                self.latest_fish = -1.0

    async def handle_embeds(self, message: discord.Message):
        for embed in message.embeds:
            if embed.title:
                if "Inventory" in embed.title and self.level == -1:
                    match = re.search(r'\*\*Level (\d+)\*\*', embed.description)
                    if match:
                        self.level = int(match.group(1))
                    for component in message.components:
                        if isinstance(component, discord.ActionRow):
                            for child in component.children:
                                if child.custom_id == "shop":
                                    self.locked = True
                                    await perform_delayed_click(child)
            if "Requirements:" in embed.description and self.locked and self.running:
                logger.info("Can't prestige yet (not matching requirements)")
                self.locked = False
                await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()
            if message.components:
                if self.locked and "/prestige reset" in embed.description:
                    if (message.interaction and message.interaction.user) and message.interaction.user == self.user:
                        if "sell everything" in embed.description:
                            self.locked = False
                            while not self.timer.has_reached(
                                    get_random_cooldown(self.cooldown)):
                                await asyncio.sleep(0.1)
                            await asyncio.sleep(random.uniform(1.10, 1.93))
                            await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()
                            self.prestige_counter.reset()
                            logger.success("Prestiged.")
                if self.prestige_counter.get() >= random.randrange(self.prestige_rate[0], self.prestige_rate[1]):
                    logger.warning("Trying to prestige...")
                    self.locked = True
                    await self.prestige_commands[self.current_channel.guild.id][self.current_channel.id]()
                if self.fish_counter.get() >= random.randrange(self.move_rate[0], self.move_rate[1]):
                    self.locked = True
                    while True:
                        self.current_channel = random.choice(self.parsed_channels)
                        try:
                            logger.warning(
                                f"Switched to {self.current_channel.name} in guild {self.current_channel.guild.name}")
                            self.timer.reset()
                            self.fish_counter.reset()
                            while not self.timer.has_reached(
                                    get_random_cooldown(self.cooldown)):
                                await asyncio.sleep(0.1)
                            await asyncio.sleep(random.uniform(1.10, 1.93))
                            self.timer.reset()
                            await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()
                            break
                        except discord.DiscordException:
                            logger.error(
                                f"Can't switch to {self.current_channel.name} in guild {self.current_channel.guild.name}")
                            pass
                    self.locked = False
            if embed.author and self.user.name in embed.author.name:
                if "captcha posted above" in embed.description:
                    await self.verify_commands[self.current_channel.guild.id][self.current_channel.id](answer="regen")
                if "**/verify** with this code" in embed.description:
                    self.locked = True
                    diff = (time.time() - self.latest_captcha) / 60
                    if diff >= 29:
                        wait_time = get_random_cooldown(60000 * (random.randint(20, 49)))
                        logger.warning(f"Got sus by mods. Waiting {wait_time} ms")
                        await asyncio.sleep(wait_time)
                        restart()
                    self.latest_captcha = time.time()
                    await self.solve_captcha(embed)
                if "You are now level" in embed.description:
                    await self.handle_level_up(embed)
                if "You found" in embed.description:
                    await self.handle_found(embed)
                if "sold" in embed.description:
                    await self.handle_sold(embed)
                if message.components:
                    await self.handle_components(message)

    async def handle_components(self, message: discord.Message):
        for component in message.components:
            if isinstance(component, discord.ActionRow):
                for child in component.children:
                    if not self.locked and self.running:
                        if ("Fish Again" in child.label and
                                any("Sell" in children.label for children in component.children)):
                            await self.handle_fish_again(child)
                        if "Sell" in child.label:
                            await self.handle_sell(child)

    async def handle_fish_again(self, child: discord.Button):
        logger.success("Fished. Waiting...")
        while not self.timer.has_reached(get_random_cooldown(self.cooldown)):
            await asyncio.sleep(0.1)
        logger.info("Fishing...")
        try:
            await child.click()
        except discord.errors.DiscordException:
            await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()
        self.latest_fish = time.time()
        self.fish_counter.update()
        self.sell_counter.update()
        self.buy_counter.update()
        self.prestige_counter.update()
        self.timer.reset()

    async def solve_captcha(self, embed: discord.Embed):
        logger.info("Trying to solve captcha using keras...")
        await asyncio.sleep(random.uniform(1.3, 2.4))
        image_url = embed.image.url
        response = requests.get(image_url)
        file_name = str("".join(random.choices(string.ascii_letters, k=8))) + ".png"
        open(file_name, 'wb').write(response.content)
        prob, answer = solver.get_answers(url=image_url)[0]
        os.remove(file_name)
        logger.success(f"Got possibly captcha answer from keras - {answer}. Probality: {prob:.2%}")
        await self.verify_commands[self.current_channel.guild.id][self.current_channel.id](answer=answer)

    async def handle_sell(self, child: discord.Button):
        if self.sell_counter.get() >= random.randrange(self.sell_rate[0], self.sell_rate[1]):
            logger.info("Selling inventory...")
            self.timer.reset()
            self.sell_counter.reset()
            try:
                await child.click()
            except discord.errors.DiscordException:
                logger.error("Can't sell inventory. Caused by another user trying to interact with bot.")

    async def handle_wait_time(self, message: discord.Message):
        wait_time = float(re.search(r"You must wait \*\*(\d+\.\d+)\*\*s", message.content).group(1))
        wait_time += random.uniform(1.0, 1.95)
        cooldown_str = re.search(r"Your cooldown: \*\*(\d+\.\d+)\*\*s", message.content).group(1)
        self.cooldown = int(float(cooldown_str) * 1000)
        logger.warning(f"Got cooldown. Updated cooldown and waiting {round(wait_time, 2)}s")
        self.locked = True
        await asyncio.sleep(wait_time)
        self.timer.reset()
        self.locked = False
        await self.fish_commands[self.current_channel.guild.id][self.current_channel.id]()

    async def handle_incorrect_code(self):
        self.captcha_attempt += 1
        if self.captcha_attempt > self.captcha_attempts:
            logger.error(
                f"Can't solve captcha (reached max attempts: {self.captcha_attempt - 1}/{self.captcha_attempts})")
            logger.error(f"Bot paused due to captcha not solved. Solve and use {BOT_PREFIX}pause command")
            self.running = False
            self.captcha_attempt = 0
            return

        logger.warning(f"Incorrect answer. Trying again... [{self.captcha_attempt}/{self.captcha_attempts}]")
        await self.verify_commands[self.current_channel.guild.id][self.current_channel.id](answer="regen")

    async def handle_level_up(self, embed: discord.Embed):
        lines = embed.description.splitlines()
        for line in lines:
            match = re.search(r"You are now level (\d+)\.", line)
            if match:
                level = int(match.group(1))
                self.level = level
                logger.success(f"Player level increased to {level}")

    @staticmethod
    async def handle_found(embed: discord.Embed):
        lines = embed.description.splitlines()
        for line in lines:
            match = re.search(r'found (an|a) (.*?) <', line)
            if match:
                article, found = match.groups()
                found = found.replace("*", "")
                logger.success(f"You found {article} {found}")

    @staticmethod
    async def handle_sold(embed: discord.Embed):
        values = re.findall(r'\$\d+(?:,\d{1,12})*', embed.description)
        logger.success(f"Sold inventory for {values[0]}. Your balance: {values[1]}")


if __name__ == '__main__':
    Entry = namedtuple('Entry', 'client, token')
    for token in BOT_TOKENS:
        bot = FishBot()
        bot.loop = asyncio.new_event_loop()
        bot.run(token)
