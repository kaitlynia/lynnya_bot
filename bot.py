import asyncio
import json
import os
from typing import Dict, List, Tuple

from aiofiles import open as aiopen
from aiofiles.threadpool.text import AsyncTextIOWrapper
from discord.errors import LoginFailure as DiscordAuthFailure
from discord.ext import commands as discord
from dotenv import load_dotenv
from twitchio.errors import AuthenticationError as TwitchAuthFailure
from twitchio.ext import commands as twitch

VERSION='0.1.0'

load_dotenv()

BOT_NAME = os.getenv('BOT_NAME')

LOG_PREFIX_INFO = os.getenv('LOG_PREFIX_INFO')
LOG_PREFIX_DONE = os.getenv('LOG_PREFIX_DONE')
LOG_PREFIX_ERROR = os.getenv('LOG_PREFIX_ERROR')
LOG_COLUMN_WIDTH = int(os.getenv('LOG_COLUMN_WIDTH'))
LOG_DATA_AS = os.getenv('LOG_DATA_AS')
LOG_TWITCH_AS = os.getenv('LOG_TWITCH_AS')
LOG_DISCORD_AS = os.getenv('LOG_DISCORD_AS')
LOG_GENERAL_AS = os.getenv('LOG_GENERAL_AS')
LOG_COLUMN_WIDTH = int(os.getenv('LOG_COLUMN_WIDTH'))
LOGIN_ATTEMPT_MESSAGE = os.getenv('LOGIN_ATTEMPT_MESSAGE')
LOGIN_SUCCESS_MESSAGE = os.getenv('LOGIN_SUCCESS_MESSAGE')
LOGIN_AUTH_ERROR_MESSAGE = os.getenv('LOGIN_AUTH_ERROR_MESSAGE')
LOGIN_ERROR_MESSAGE = os.getenv('LOGIN_ERROR_MESSAGE')

DATA_PATH = os.getenv('DATA_PATH')

TWITCH_TOKEN = os.getenv('TWITCH_TOKEN')
BROADCASTER_CHANNEL = os.getenv('BROADCASTER_CHANNEL')

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_STAFF_CHANNEL_ID = int(os.getenv('DISCORD_STAFF_CHANNEL_ID'))
DISCORD_CHANNEL_IDS = set(map(int, os.getenv('DISCORD_CHANNEL_IDS').split(',')))

DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX')

def print_box(message: str):
  l = len(message)
  print(
    '┏━' + '━' * l + '━┓',
    '┃ ' + message + ' ┃',
    '┗━' + '━' * l + '━┛',
    sep='\n'
  )

def log(prefix: str, origin: str, *info: str):
  print(f'{prefix} {origin}{" " * max(1, LOG_COLUMN_WIDTH - len(origin))}{"".join(info)}')


class Loggable:
  log_as = LOG_GENERAL_AS

  def log_info(self, *info):
    log(LOG_PREFIX_INFO, self.log_as, *info)
  def log_done(self, *info):
    log(LOG_PREFIX_DONE, self.log_as, *info)
  def log_error(self, *info):
    log(LOG_PREFIX_ERROR, self.log_as, *info)

class Data(dict, Loggable):
  log_as = LOG_DATA_AS
  defaults = {
    'twitch_prefix': DEFAULT_PREFIX,
    'discord_prefix': DEFAULT_PREFIX
  }

  def __init__(self, path: str):
    super().__init__()
    self.path = path
  
  async def __read_dict_from_file(self, aiof: AsyncTextIOWrapper):
    return json.loads(await aiof.read())
  async def __write_dict_to_file(self, obj: dict, aiof: AsyncTextIOWrapper):
    await aiof.write(json.dumps(obj))

  async def load(self):
    self.log_info('loading data')
    try:
      async with aiopen(self.path) as aiof:
        self.clear()
        self.update(await self.__read_dict_from_file(aiof))
      self.log_done('loaded data')
    except FileNotFoundError:
      self.log_error('file not found, creating a new data file')
      async with aiopen(self.path, 'w') as aiof:
        await self.__write_dict_to_file(self.defaults, aiof)
        self.clear()
      self.log_done('created file')
    except Exception as exc:
      self.log_error('an unexpected error occurred while loading data:')
      raise exc

  async def save(self):
    self.log_info('saving data')
    try:
      async with aiopen(self.path, 'w') as aiof:
        await self.__write_dict_to_file(self, aiof)
      self.log_done('saved data')
    except Exception as exc:
      self.log_error('an error occurred while saving data:')
      raise exc


class CommandFrame:
  def __init__(self, ctx):
    if type(ctx) is discord.Context:
      pass
    elif type(ctx) is twitch.Context:
      pass
    else:
      raise RuntimeError('unsupported command frame type ID: {command_frame_type}')


class TwitchBot(twitch.Bot, Loggable):
  log_as = LOG_TWITCH_AS

  def __init__(self, token: str, data: Data):
    super().__init__(
      token=token,
      prefix=data.get('twitch_prefix', DEFAULT_PREFIX),
      initial_channels=[BROADCASTER_CHANNEL]
    )
    self.data = data
  
  async def connect(self):
    self.log_info(LOGIN_ATTEMPT_MESSAGE)
    try:
      await super().connect()
      self.log_done(LOGIN_SUCCESS_MESSAGE)
    except TwitchAuthFailure:
      self.log_error(LOGIN_AUTH_ERROR_MESSAGE)
    except Exception as exc:
      self.log_error(LOGIN_ERROR_MESSAGE)
      raise exc

  async def event_ready(self):
    self.log_done('ready')

  @twitch.command()
  async def code(self, ctx: twitch.Context):
    if ctx.author.is_mod and len(ctx.args) > 1:
      self.data['lobby_code'] = ctx.args[1]
      await self.data.save()
      await ctx.send('Lobby code updated!')
    else:
      await ctx.send(f'Lobby code: {self.data.get("lobby_code", "n/a")}')
  @twitch.command()
  async def ddnet(self, ctx: twitch.Context):
    await ctx.send('DDNet player profile: https://ddnet.tw/players/lynn')
  @twitch.command(name='discord')
  async def discord_command(self, ctx: twitch.Context):
    await ctx.send('Join lynnya\'s lair! https://discord.gg/yZ7jDVjS4N (or DM lynn#3368)')
  @twitch.command()
  async def donate(self, ctx: twitch.Context):
    await ctx.send('Donate to lynnya: https://streamlabs.com/lynnya_tw')
  @twitch.command()
  async def faq(self, ctx: twitch.Context):
    await ctx.send('FAQ: https://pastebin.com/g1PGbhzi')
  @twitch.command()
  async def mc(self, ctx: twitch.Context):
    await ctx.send('Join lynnSMP! teehou.se:25566 (Minecraft 1.16.5, DM lynn#3368 to be whitelisted)')
  @twitch.command()
  async def ip(self, ctx: twitch.Context):
    await ctx.send('Join lynnSMP! teehou.se:25566 (Minecraft 1.16.5, DM lynn#3368 to be whitelisted)')
  @twitch.command()
  async def survey(self, ctx: twitch.Context):
    await ctx.send('Please fill out this survey! I do read the responses and your feedback is valuable to me <3 https://forms.gle/JiZTyFwAmkHsYXUPA')
  @twitch.command()
  async def lcsg(self, ctx: twitch.Context):
    await ctx.send('Tournament rules: https://pastebin.com/ZPRs5eYH')
  @twitch.command()
  async def tourney(self, ctx: twitch.Context):
    await ctx.send('Tournament rules: https://pastebin.com/ZPRs5eYH')
  @twitch.command()
  async def twitter(self, ctx: twitch.Context):
    await ctx.send('Follow for stream notifications, updates, and bad cat puns: https://twitter.com/lynnya_twitch')
  @twitch.command()
  async def youtube(self, ctx: twitch.Context):
    await ctx.send('Subscribe to lynnya on YouTube: https://www.youtube.com/channel/UC2b407ERbwp4_PZ4TDRn1xg')


class DiscordBot(discord.Bot, Loggable):
  log_as = LOG_DISCORD_AS

  def __init__(self, data: Data):
    super().__init__(command_prefix=data.get('discord_prefix', DEFAULT_PREFIX))
    self.data = data

  async def login(self, token: str):
    self.log_info(LOGIN_ATTEMPT_MESSAGE)
    try:
      await super().login(token)
      self.log_done(LOGIN_SUCCESS_MESSAGE)
    except DiscordAuthFailure:
      self.log_error(LOGIN_AUTH_ERROR_MESSAGE)
    except Exception as exc:
      self.log_error(LOGIN_ERROR_MESSAGE)
      raise exc

  async def on_ready(self):
    self.log_done('ready')

async def main():
  print_box(f'{BOT_NAME} v{VERSION}')

  data = Data(DATA_PATH)
  await data.load()

  discord_bot = DiscordBot(data)

  @discord_bot.check
  async def limit_commands_to_channels(ctx: discord.Context):
      return ctx.guild is not None and ctx.channel.id in DISCORD_CHANNEL_IDS
  
  def edit_command_perms(ctx: discord.Context, arg):
    return ctx.author.permissions_in(ctx.bot.get_channel(DISCORD_STAFF_CHANNEL_ID)).view_channel and arg != ''

  @discord_bot.command(name='code')
  async def code_command(ctx: discord.Context, code: str=''):
    if edit_command_perms(ctx, code):
      ctx.bot.data['lobby_code'] = code
      await ctx.bot.data.save()
      await ctx.send('Lobby code updated!')
    else:
      await ctx.send(f'Lobby code: {ctx.bot.data.get("lobby_code", "n/a")}')
  @discord_bot.command()
  async def ddnet(ctx: discord.Context):
    await ctx.send('DDNet player profile: https://ddnet.tw/players/lynn')
  @discord_bot.command(name='discord')
  async def discord_command(ctx: discord.Context):
    await ctx.send('Join lynnya\'s lair! <https://discord.gg/yZ7jDVjS4N> (or DM lynn#3368)')
  @discord_bot.command()
  async def donate(ctx: discord.Context):
    await ctx.send('Donate to lynnya: https://streamlabs.com/lynnya_tw')
  @discord_bot.command()
  async def faq(ctx: discord.Context):
    await ctx.send('FAQ: https://pastebin.com/g1PGbhzi')
  @discord_bot.command()
  async def mc(ctx: discord.Context):
    await ctx.send('Join lynnSMP! teehou.se:25566 (Minecraft 1.16.5, DM lynn#3368 to be whitelisted)')
  @discord_bot.command()
  async def ip(ctx: discord.Context):
    await ctx.send('Join lynnSMP! teehou.se:25566 (Minecraft 1.16.5, DM lynn#3368 to be whitelisted)')
  @discord_bot.command()
  async def survey(ctx: discord.Context):
    await ctx.send('Please fill out this survey! I do read the responses and your feedback is valuable to me <3 https://forms.gle/JiZTyFwAmkHsYXUPA')
  @discord_bot.command()
  async def lcsg(ctx: discord.Context):
    await ctx.send('Tournament rules: https://pastebin.com/ZPRs5eYH')
  @discord_bot.command()
  async def tourney(ctx: discord.Context):
    await ctx.send('Tournament rules: https://pastebin.com/ZPRs5eYH')
  @discord_bot.command()
  async def twitter(ctx: discord.Context):
    await ctx.send('Follow for stream notifications, updates, and bad cat puns: https://twitter.com/lynnya_twitch')
  @discord_bot.command()
  async def youtube(ctx: discord.Context):
    await ctx.send('Subscribe to lynnya on YouTube: https://www.youtube.com/channel/UC2b407ERbwp4_PZ4TDRn1xg')

  await discord_bot.login(DISCORD_TOKEN)

  twitch_bot = TwitchBot(TWITCH_TOKEN, data)

  await asyncio.gather(*(bot.connect() for bot in [twitch_bot, discord_bot]))

if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    exit()