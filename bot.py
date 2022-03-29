import asyncio
import json
import os
import random
import re
import time

from aiofiles import open as aiopen
from aiofiles.threadpool.text import AsyncTextIOWrapper
from discord.errors import LoginFailure as DiscordAuthFailure
from discord.ext import commands as discord
from dotenv import load_dotenv
from peony import PeonyClient
from twitchio import Message as TwitchMessage
from twitchio.errors import AuthenticationError as TwitchAuthFailure
from twitchio.ext import commands as twitch

VERSION='0.1.4'

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
DISCORD_BROADCASTER_ID = int(os.getenv('DISCORD_BROADCASTER_ID'))
DISCORD_STAFF_CHANNEL_ID = int(os.getenv('DISCORD_STAFF_CHANNEL_ID'))
DISCORD_SUBSCRIBER_ROLE_ID = int(os.getenv('DISCORD_SUBSCRIBER_ROLE_ID'))
DISCORD_ALERTS_CHANNEL_ID = int(os.getenv('DISCORD_ALERTS_CHANNEL_ID'))
DISCORD_ALERTS_ROLE_ID = int(os.getenv('DISCORD_ALERTS_ROLE_ID'))
DISCORD_CLOSED_VOICE_CHANNEL_ID = int(os.getenv('DISCORD_CLOSED_VOICE_CHANNEL_ID'))
DISCORD_LIVE_VOICE_CHANNEL_ID = int(os.getenv('DISCORD_LIVE_VOICE_CHANNEL_ID'))
DISCORD_CHANNEL_IDS = set(map(int, os.getenv('DISCORD_CHANNEL_IDS').split(',')))

TWITTER_KEY = os.getenv('TWITTER_KEY')
TWITTER_SECRET = os.getenv('TWITTER_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

DISCORD_ALERT_FORMAT = '<@&{}>\n\n{} ({})\n\nhttps://twitch.tv/{}'
TWITTER_ALERT_FORMAT = '{} ({})\n\nhttps://twitch.tv/{}'

DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX')
DEFAULT_CURRENCY_EMOJI = os.getenv('DEFAULT_CURRENCY_EMOJI')

DISCORD_PREFIX_KEY = 'prefix:discord'
TWITCH_PREFIX_KEY = 'prefix:twitch'

RARITY_COMMON = 'Common'
RARITY_UNCOMMON = 'Uncommon'
RARITY_RARE = 'Rare'
RARITY_MYTHIC = 'Mythic'
RARITY_LEGENDARY = 'Legendary'

INVENTORY_TEMPLATE = 'Inventory:\n```md\n{}\n```'

EMOTE_VALUE_EXPONENT = 0.5
PARTIAL_BAL_PER_BAL = 10

# load English word list TODO: extend this to include common tokens used in chats (uwu, IRL, etc.)
with open('words.txt') as f:
  ENGLISH_WORDS = set(f.read().lower().split())

def print_box(message: str):
  l = len(message)
  print(
    '┏━' + '━' * l + '━┓',
    '┃ ' + message + ' ┃',
    '┗━' + '━' * l + '━┛',
    sep='\n'
  )

# levenshtein distance function. used to determine word values for chatter rewards
# source: https://devrescue.com/levenshtein-distance-in-python
def leven(x, y):
  n = len(x)
  m = len(y)
  A = [[i + j for j in range(m + 1)] for i in range(n + 1)]

  for i in range(n):
    for j in range(m):
      A[i + 1][j + 1] = min(
        A[i][j + 1] + 1,              # insert
        A[i + 1][j] + 1,              # delete
        A[i][j] + int(x[i] != y[j])   # replace
      )
  return A[n][m]

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
    TWITCH_PREFIX_KEY: DEFAULT_PREFIX,
    DISCORD_PREFIX_KEY: DEFAULT_PREFIX,
    'currency_emoji': DEFAULT_CURRENCY_EMOJI,
    'bal:sorted': []
  }

  def __init__(self, path: str):
    super().__init__()
    self.path = path

  async def __read_dict_from_file(self, aiof: AsyncTextIOWrapper):
    return self.defaults | json.loads(await aiof.read())
  async def __write_dict_to_file(self, obj: dict, aiof: AsyncTextIOWrapper):
    await aiof.write(json.dumps(obj, indent=2, sort_keys=True))

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

    async with aiopen(self.path) as aiof:
      backup = await self.__read_dict_from_file(aiof)

    try:
      async with aiopen(self.path, 'w') as aiof:
        await self.__write_dict_to_file(self, aiof)
      self.log_done('saved data')
    except Exception as exc:
      async with aiopen(self.path, 'w') as aiof:
        await self.__write_dict_to_file(backup, aiof)

      self.log_error('an error occurred while saving data:')
      raise exc


class AllContext:
  def __init__(self, discord_bot: discord.Bot, twitch_bot: twitch.Bot, ctx, data: Data):
    self.discord_bot = discord_bot
    self.twitch_bot = twitch_bot
    self.source_ctx = ctx
    self.data = data

    self.source_id = int(ctx.author.id) if type(ctx.author.id) is str else ctx.author.id
    self.source_type = type(ctx)
    self.system_content = None
    self.clean_content = None
    self.is_mod = None
    self.is_subscriber = None

    self.user_id = None
    self.reply = None

    # context check to populate user_id
    if self.source_type is discord.Context:
      self.is_mod = ctx.author.permissions_in(ctx.bot.get_channel(DISCORD_STAFF_CHANNEL_ID)).view_channel

      self.system_content = ctx.message.system_content
      self.clean_content = ctx.message.clean_content
      self.timestamp = ctx.message.created_at.timestamp()

      discord_to_twitch_key = f'discord:{self.source_id}'
      if discord_to_twitch_key in data:
        self.user_id = data[discord_to_twitch_key]

        async def check_sub():
          # has_sub_role = any(role.id == DISCORD_SUBSCRIBER_ROLE_ID for role in ctx.author.roles)
          # if not has_sub_role:
          #   matched_users = await self.twitch_bot.fetch_users(ids=[self.user_id])
          #   if len(matched_users) > 0:
              # return matched_users[0].is_subscriber
          # return has_sub_role
          return any(role.id == DISCORD_SUBSCRIBER_ROLE_ID for role in ctx.author.roles)

        self.check_sub = check_sub

      else:
        async def check_sub():
          return any(role.id == DISCORD_SUBSCRIBER_ROLE_ID for role in ctx.author.roles)

        self.check_sub = check_sub

      async def __reply(content: str):
        formatted = content.replace('/>', '>')
        await ctx.reply(formatted)

      self.reply = __reply

    elif self.source_type is twitch.Context:
      self.is_mod = ctx.author.is_mod

      async def check_sub():
        return ctx.author.is_subscriber

      self.check_sub = check_sub

      self.system_content = ctx.message.raw_data
      self.clean_content = ctx.message.raw_data
      self.timestamp = ctx.message.timestamp.timestamp()

      self.user_id = self.source_id

      async def __reply(content: str):
        formatted = ' | '.join(filter(
          None, content\
            .replace('***', '')\
            .replace('**', '')\
            .replace('`', '')\
            .replace('<http', 'http')\
            .replace('/>', '')\
            .split('\n')
        ))
        await ctx.reply(formatted)

      self.reply = __reply

    else:
      raise RuntimeError(f'unsupported context type: {type(ctx)}')

  @property
  def prefix(self):
    if self.source_type is discord.Context:
      return self.data[DISCORD_PREFIX_KEY]
    elif self.source_type is twitch.Context:
      return self.data[TWITCH_PREFIX_KEY]
    else:
      raise RuntimeError(f'unknown prefix for source type: {type(self.source_type)}')


class TwitchBot(twitch.Bot, Loggable):
  log_as = LOG_TWITCH_AS

  def __init__(self, token: str, data: Data):
    super().__init__(
      token=token,
      prefix=data['prefix:twitch'],
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

  async def event_command_error(self, ctx, error):
    if isinstance(error, twitch.CommandNotFound):
      return
    raise error

  async def event_ready(self):
    self.log_done('ready')


class DiscordBot(discord.Bot, Loggable):
  log_as = LOG_DISCORD_AS

  def __init__(self, data: Data):
    super().__init__(command_prefix=data[DISCORD_PREFIX_KEY])
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

  async def on_command_error(self, ctx, error):
    if isinstance(error, discord.CommandNotFound):
      return
    raise error.original

  async def on_ready(self):
    self.log_done('ready')

async def main():
  print_box(f'{BOT_NAME} v{VERSION}')

  data = Data(DATA_PATH)
  await data.load()

  discord_bot = DiscordBot(data)
  twitch_bot = TwitchBot(TWITCH_TOKEN, data)
  twitter_bot = PeonyClient(
    TWITTER_KEY,
    TWITTER_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET
  )

  def add_command(coro, name=None):
    @twitch_bot.command(name=name or coro.__name__.replace('_command', ''))
    async def __twitch_command(ctx, *args):
      await coro(AllContext(discord_bot, twitch_bot, ctx, data), *args)

    @discord_bot.command(name=name or coro.__name__.replace('_command', ''))
    async def __discord_command(ctx, *args):
      await coro(AllContext(discord_bot, twitch_bot, ctx, data), *args)

  def add_commands(*coros):
    for coro in coros:
      add_command(coro)

  async def is_live(channel_name: str = BROADCASTER_CHANNEL):
    return bool(await twitch_bot.fetch_streams(user_logins=[channel_name]))

  async def basic_command(ctx: AllContext, key: str, label: str, intro: str, *args, unavailable='n/a'):
    if ctx.is_mod and len(args):
      data[key] = ' '.join(args)
      await data.save()
      await ctx.reply(f'{label} updated!')
    else:
      await ctx.reply(f'{intro}{data.get(key, unavailable)}')

  async def reply_not_linked(ctx: AllContext):
    return await ctx.reply(f'This command requires a linked Discord account. Use {data[DISCORD_PREFIX_KEY]}link in Discord to link your accounts.')

  @discord_bot.event
  async def on_voice_state_update(member, before, after):
    if member.id == DISCORD_BROADCASTER_ID:
      if before.channel is not None and \
        before.channel.id == DISCORD_LIVE_VOICE_CHANNEL_ID and \
        (after.channel is None or after.channel.id != DISCORD_LIVE_VOICE_CHANNEL_ID):

        reason = 'broadcaster left LIVE channel'
        guild = before.channel.guild
        live_voice_channel = before.channel
        closed_voice_channel = guild.get_channel(DISCORD_CLOSED_VOICE_CHANNEL_ID)

        discord_bot.log_info('disabling LIVE channel for members')
        await live_voice_channel.set_permissions(guild.default_role, view_channel=False, connect=False, reason=reason)
        discord_bot.log_done('disabled LIVE')
        if (num_members := len(live_voice_channel.members)):
          discord_bot.log_info(f'moving {num_members} members')
          move_gen = (m.move_to(closed_voice_channel, reason=reason) for m in live_voice_channel.members)
          await asyncio.gather(*move_gen)
          discord_bot.log_done('moved members')

      elif after.channel is not None and \
        after.channel.id == DISCORD_LIVE_VOICE_CHANNEL_ID and \
        (before.channel is None or before.channel.id != DISCORD_LIVE_VOICE_CHANNEL_ID):

        reason = 'broadcaster joined LIVE channel'
        live_voice_channel = after.channel

        discord_bot.log_info('enabling LIVE channel for members')
        await live_voice_channel.set_permissions(live_voice_channel.guild.default_role, view_channel=True, connect=False)
        discord_bot.log_done('enabled LIVE')

  @discord_bot.check
  async def __limit_commands_to_channels(ctx: discord.Context):
    return ctx.guild is not None and ctx.channel.id in DISCORD_CHANNEL_IDS

  # on message, do chatter-based logic here
  @twitch_bot.event()
  async def event_message(message: TwitchMessage):
    if message.author is None or message.author.name == twitch_bot.nick or not await is_live(): return

    # everything after "emotes="
    emote_pre = message.raw_data.split('emotes=', 1)[-1]
    # ... everything after the message head
    tokens_str = emote_pre.split(' PRIVMSG ')[-1].split(':')[-1]
    # ... and everything before the emote value delimiter (;)
    emote_blob = emote_pre.split(';', 1)[0]
    num_emotes = 0
    unique_emotes = []

    if emote_blob:
      # for emote type in list of unique emotes used
      for emote_type in emote_blob.split('/'):
        # find all the ranges the emote was used in
        ranges_used = emote_type.split(':')[-1].split(',')
        # +1 for each range
        num_emotes += len(ranges_used)
        # use the first available range to record the emote's name for removal later
        start, stop = map(int, ranges_used[0].split('-'))
        unique_emotes.append(tokens_str[start : stop + 1])

    # remove emotes
    for emote in unique_emotes:
      tokens_str.replace(emote, '')

    # remove symbols, remove capitals, then tokenize
    tokens = re.sub(r'[^\w+]', ' ', tokens_str).lower().split()

    # remove duplicate tokens, then remove tokens that are not known to be English words
    words = list(t for t in set(tokens) if t in ENGLISH_WORDS)
    num_words = len(words)

    # find the average of averages for each word's levenshtein distances to other words in the message
    # NOTE: this is a SOMEWHAT accurate way of determining valuable/conversational messages, but it is not ideal
    words_score = sum(sum(leven(word, w) for w in words) / num_words for word in words) / num_words if num_words else 0

    # calculate total score with the emote score combined
    total_score = int(words_score + num_emotes ** EMOTE_VALUE_EXPONENT)

    partial_bal_key = f'partial_bal:{message.author.id}'
    partial_bal = data[partial_bal_key] = data.get(partial_bal_key, 0) + total_score

    if partial_bal >= PARTIAL_BAL_PER_BAL:
      data[partial_bal_key] = partial_bal - PARTIAL_BAL_PER_BAL
      bal_key = f'bal:{message.author.id}'
      data[bal_key] = data.get(bal_key, 0) + 1

    await data.save()


  #################
  ### RPG LOGIC ###
  #################

  '''LOOT BOX EXPLANATION:
- each loot box is assigned a rarity value when purchased
- loot boxes can be traded for other items or sold for flowers
- loot boxes with higher rarity values have higher odds of dropping rare items


reforge costs flowers
enhancing costs scape (dismantle shitty items, except pets which can only be sold or traded)


RARITY VALUES:
- Legendary (1% scalar)
- Mythic (5% scalar)
- Rare (15% scalar)
- Uncommon (40% scalar)
- Common'''

  async def create_loot_box(ctx: AllContext):
    roll = random.random()

    box = {
      'source_canonical_id': ctx.user_id,
      'source_id': ctx.source_id,
      'timestamp': ctx.timestamp,
      'was_subscriber': await ctx.check_sub(),
      'name': 'Loot Box',
      'rarity': None
    }

    if roll < 0.01:
      box['rarity'] = RARITY_LEGENDARY
    elif roll < 0.05:
      box['rarity'] = RARITY_MYTHIC
    elif roll < 0.15:
      box['rarity'] = RARITY_RARE
    elif roll < 0.4:
      box['rarity'] = RARITY_UNCOMMON
    else:
      box['rarity'] = RARITY_COMMON

    return box

  weapons_summary = '''
  - Shortsword: 1
  - Javelin: 2
  - Mace: 3
  - Crossbow: 3 (base 10% attack speed)
  - Magic Missle: 5 (base 10% attack speed + mana cost: 20 mana)
  - Plasma Cannon: 5 (base 20% attack speed + base 10% electric damage)
  - Ice Bow: 5 (base 20% attack speed + base 10% freeze damage)
  - Poisoned Saber: 7 (base 10% poison damage)
  - Poison Staff: 7 (base 20% poison damage + mana cost: 35 mana)
  - Ignition Spell: 7 (base 20% burn damage + mana cost: 35 mana)
  - Frost Bolt: 7 (base 20% freeze damage + mana cost: 35 mana)
  - Fire Sword: 7 (base 10% burn damage)
  - Tome of Thunder: 8 (base 10% electric damage + mana cost: 40 mana)
  - Broadsword: 8 (base -10% attack speed)
  - Battleaxe: 10 (base -20% attack speed)
  - Bane of Souls: 11 (base 10% life steal + mana cost: 60 mana)'''

  weapons = [
    {'name': 'Shortsword', 'damage': 1},
    {'name': 'Javelin', 'damage': 2},
    {'name': 'Mace', 'damage': 3},
    {'name': 'Crossbow', 'effect': 'rate', 'effect_value': 10, 'damage': 3},
    {'name': 'Magic Missle', 'mana_cost': 20, 'effect': 'rate', 'effect_value': 10, 'damage': 5},
    {'name': 'Plasma Cannon', 'effect': 'rate', 'effect_value': 20, 'effect_2': 'electric', 'effect_value_2': 10, 'damage': 5},
    {'name': 'Ice Bow', 'effect': 'rate', 'effect_value': 20, 'effect_2': 'freeze', 'effect_value_2': 10, 'damage': 5},
    {'name': 'Poisoned Saber', 'effect': 'poison', 'effect_value': 10, 'damage': 7},
    {'name': 'Poison Staff', 'mana_cost': 35, 'effect': 'poison', 'effect_value': 20, 'damage': 7},
    {'name': 'Ignition Spell', 'mana_cost': 35, 'effect': 'burn', 'effect_value': 20, 'damage': 7},
    {'name': 'Frost Bolt', 'mana_cost': 35, 'effect': 'freeze', 'effect_value': 20, 'damage': 7},
    {'name': 'Fire Sword', 'effect': 'burn', 'effect_value': 10, 'damage': 7},
    {'name': 'Tome of Thunder', 'mana_cost': 40, 'effect': 'electric', 'effect_value': 10, 'damage': 8},
    {'name': 'Broadsword', 'effect': 'rate', 'effect_value': -10, 'damage': 8},
    {'name': 'Battleaxe', 'effect': 'rate', 'effect_value': -20, 'damage': 10},
    {'name': 'Bane of Souls', 'effect': 'life_steal', 'effect_value': 10, 'mana_cost': 60, 'damage': 11}
  ]

  armor_summary = '''
  - Leather: 1
  - Iron: 2
  - Mythril: 4
  - Titanium: 5
  - Spectral: 5 (20% evade chance)'''

  armor = [
    {'name': 'Leather', 'defense': 1},
    {'name': 'Iron', 'defense': 2},
    {'name': 'Mythril', 'defense': 4},
    {'name': 'Titanium', 'defense': 5},
    {'name': 'Spectral', 'effect': 'evade', 'effect_value': 20, 'defense': 5}
  ]

  pets_summary = '''
  - Cat: 1
  - Snake: 2
  - Dog: 2
  - Fairy: 2 (20% mana recovery)
  - Wolf: 3
  - Bear: 4
  - Crocodile: 4
  - Lion: 5
  - Tiger: 6
  - Raptor: 7 (10% poison damage)
  - Giant: 8
  - Golem: 9
  - Wyvern: 10 (20% total mana)
  - Phoenix: 11 (10% fire damage)
  - Dragon: 12 (10% fire damage)'''

  pets = [
    {'name': 'Cat', 'damage': 1},
    {'name': 'Snake', 'damage': 2},
    {'name': 'Dog', 'damage': 2},
    {'name': 'Fairy', 'effect': 'mana_rec', 'effect_value': 20, 'damage': 2},
    {'name': 'Wolf', 'damage': 3},
    {'name': 'Bear', 'damage': 4},
    {'name': 'Crocodile', 'damage': 4},
    {'name': 'Lion', 'damage': 5},
    {'name': 'Tiger', 'damage': 6},
    {'name': 'Raptor', 'effect': 'poison', 'effect_value': 10, 'damage': 7},
    {'name': 'Giant', 'damage': 8},
    {'name': 'Golem', 'damage': 9},
    {'name': 'Wyvern', 'effect': 'mana', 'effect_value': 20, 'damage': 10},
    {'name': 'Phoenix', 'effect': 'burn', 'effect_value': 10, 'damage': 11},
    {'name': 'Dragon', 'effect': 'burn', 'effect_value': 20, 'damage': 12}
  ]

  gems_summary = '''
  - Amethyst: (10% HP recovery)
  - Garnet: (20% total HP)
  - Sapphire: (20% mana recovery)
  - Opal: (20% total mana)
  - Emerald: (10% attack rate)
  - Agate: (5% attack buff)
  - Jade: (10% defense buff)
  - Ruby: (10% burn damage)
  - Tourmaline: (10% poison damage)
  - Crystal: (10% freeze damage)
  - Citrine: (10% electric damage)'''

  gems = [
    {'name': 'Amethyst', 'effect': 'hp_rec', 'effect_value': 10},
    {'name': 'Garnet', 'effect': 'hp', 'effect_value': 20},
    {'name': 'Sapphire', 'effect': 'mana_rec', 'effect_value': 20},
    {'name': 'Opal', 'effect': 'mana', 'effect_value': 20},
    {'name': 'Emerald', 'effect': 'rate', 'effect_value': 10},
    {'name': 'Agate', 'effect': 'attack', 'effect_value': 5},
    {'name': 'Jade', 'effect': 'defense', 'effect_value': 10},
    {'name': 'Ruby', 'effect': 'burn', 'effect_value': 10},
    {'name': 'Tourmaline', 'effect': 'poison', 'effect_value': 10},
    {'name': 'Crystal', 'effect': 'freeze', 'effect_value': 10},
    {'name': 'Citrine', 'effect': 'electric', 'effect_value': 10}
  ]


  ################
  ### COMMANDS ###
  ################

  async def code_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:lobby', 'Lobby code', 'Lobby code: ', *args)
  async def ddnet_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:ddnet', 'DDNet profile', 'DDNet player profile: ', *args)
  async def discord_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:discord', 'Discord server', 'Join lynnya\'s lair! ', *args)
  async def donate_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:donate', 'Donate link', 'Donate to lynnya: ', *args)
  async def faq_command(ctx: AllContext,  *args):
    await basic_command(ctx, 'info:faq', 'FAQ link', 'FAQ: ', *args)
  async def mc_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:mc', 'Minecraft server info', 'Join lynnSMP! ', *args)
  async def ip_command(ctx: AllContext, *args):
    await mc_command(ctx, *args)
  async def survey_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:survey', 'Survey info', 'Please fill out this survey! ', *args)
  async def tournament_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:tournament', 'Tournament info', 'Tournament rules: ', *args)
  async def tourney_command(ctx: AllContext, *args):
    await tournament_command(ctx, *args)
  async def lcsg_command(ctx: AllContext, *args):
    await tournament_command(ctx, *args)
  async def twitter_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:twitter', 'Twitter link', 'Follow for stream notifications, updates, and bad cat puns: ', *args)
  async def youtube_command(ctx: AllContext, *args):
    await basic_command(ctx, 'info:youtube', 'YouTube link', 'Subscribe to lynnya on YouTube: ', *args)

  async def edit_command(ctx: AllContext, *args):
    if ctx.is_mod:
      if len(args) < 2:
        return await ctx.reply('Missing info message argument.')
      name = args[0]
      data[f'info:{name}'] = ' '.join(args[1:])
      await ctx.reply(f'Info for "{name}" updated!')

  async def link_command(ctx: AllContext, *code):
    if ctx.source_type is discord.Context:
      discord_to_twitch_key = f'discord:{ctx.source_id}'
      if discord_to_twitch_key in data:
        await ctx.reply('Your Discord account is already linked.')
      else:
        code = '%030x' % random.randrange(16**30)
        data[f'link_code:{code}'] = ctx.source_id
        link_for_key = f'link_for:{ctx.source_id}'
        if link_for_key in data:
          del data[f'link_code:{data[link_for_key]}']
        data[link_for_key] = code
        await data.save()
        await (await discord_bot.fetch_user(ctx.source_id)).send(f'Use `{data["prefix:twitch"]}link {code}` in Twitch chat (<https://twitch.tv/{BROADCASTER_CHANNEL}/>) to link your account.')
        await ctx.reply('A link code has been sent to you in a direct message.')
    elif ctx.source_type is twitch.Context:
      if len(code):
        try:
          link_key = f'link_code:{code[0]}'
          discord_id = data[link_key]
          data[f'discord:{discord_id}'] = ctx.source_id
          del data[f'link_for:{discord_id}']
          del data[link_key]
          await data.save()
          await ctx.reply('Your Discord account was successfully linked!')
        except KeyError:
          await ctx.reply('Invalid code.')
      else:
        await ctx.reply(f'Missing code argument. Use {data[DISCORD_PREFIX_KEY]}link in Discord to link your accounts.')

  async def status_command(ctx: AllContext, *args):
    twitch_channel = await twitch_bot.fetch_channel(BROADCASTER_CHANNEL)
    online = await is_live()
    status = '**Online**' if online else 'Offline'
    stream_link = f'https://twitch.tv/{BROADCASTER_CHANNEL}'
    stream_link_embedded = stream_link if online else f'<{stream_link}/>'
    await ctx.reply(f'''{status}
**Title:** {twitch_channel.title}
**Game:** ({twitch_channel.game_name})
**Stream:** {stream_link_embedded}''')

  async def alert_command(ctx: AllContext, *args):
    if ctx.is_mod:
      twitch_channel = await twitch_bot.fetch_channel(BROADCASTER_CHANNEL)
      alerts_channel = discord_bot.get_channel(DISCORD_ALERTS_CHANNEL_ID)

      await alerts_channel.send(DISCORD_ALERT_FORMAT.format(
        DISCORD_ALERTS_ROLE_ID,
        twitch_channel.title,
        twitch_channel.game_name,
        BROADCASTER_CHANNEL
      ))

      response = await twitter_bot.api.statuses.update.post(status=TWITTER_ALERT_FORMAT.format(
        twitch_channel.title,
        twitch_channel.game_name,
        BROADCASTER_CHANNEL
      ))

      # print(f'https://twitter.com/{response.user.screen_name}/{response.id}')
      # {'created_at': 'Sat Dec 04 22:33:57 +0000 2021', 'id': 1467260917981200385, 'id_str':
      # '1467260917981200385', 'text': 'ttyd! playing through some of chapter 3 and then crab
      # game (Paper Mario: The Thousand-Year Door)\n\nhttps://t.co/ydk3O46NoP', 'truncated': False, 'entities': {'hashtags': [], 'symbols': [], 'user_mentions': [], 'urls': [{'url': 'https://t.co/ydk3O46NoP', 'expanded_url': 'https://twitch.tv/lynnya_tw', 'display_url': 'twitch.tv/lynnya_tw', 'indices': [98, 121]}]}, 'source': '<a href="https://help.twitter.com/en/using-twitter/how-to-tweet#source-labels" rel="nofollow">lynnya_tw</a>', 'in_reply_to_status_id': None, 'in_reply_to_status_id_str': None, 'in_reply_to_user_id': None, 'in_reply_to_user_id_str': None, 'in_reply_to_screen_name': None, 'user': {'id': 1456396235951075336, 'id_str': '1456396235951075336', 'name': 'lynnya', 'screen_name': 'lynnya_twitch', 'location': 'she/her', 'description': "hi everyone! i'm lynnya, a virtual catgirl! #VTuber @ https://t.co/VKJSaaEtpA | https://t.co/QVyqbPExUi | https://t.co/aRQR4NxM8p…", 'url': 'https://t.co/v1aPUrnenA', 'entities': {'url': {'urls': [{'url': 'https://t.co/v1aPUrnenA', 'expanded_url': 'https://twitch.tv/lynnya_tw', 'display_url': 'twitch.tv/lynnya_tw', 'indices': [0, 23]}]}, 'description': {'urls': [{'url': 'https://t.co/VKJSaaEtpA', 'expanded_url': 'http://twitch.tv/lynnya_tw', 'display_url': 'twitch.tv/lynnya_tw', 'indices': [54, 77]}, {'url': 'https://t.co/QVyqbPExUi', 'expanded_url': 'http://discord.gg/yZ7jDVjS4N', 'display_url': 'discord.gg/yZ7jDVjS4N', 'indices': [80, 103]}, {'url': 'https://t.co/aRQR4NxM8p', 'expanded_url': 'http://youtube.com/channel/UC2b40', 'display_url': 'youtube.com/channel/UC2b40', 'indices': [106, 129]}]}}, 'protected': False, 'followers_count': 14, 'friends_count': 0, 'listed_count': 0, 'created_at': 'Thu Nov 04 23:01:40 +0000 2021', 'favourites_count': 0, 'utc_offset': None, 'time_zone': None, 'geo_enabled': False, 'verified': False, 'statuses_count': 54, 'lang': None, 'contributors_enabled': False, 'is_translator': False, 'is_translation_enabled': False, 'profile_background_color': 'F5F8FA', 'profile_background_image_url': None, 'profile_background_image_url_https': None, 'profile_background_tile': False, 'profile_image_url': 'http://pbs.twimg.com/profile_images/1456396286144307204/8SW-1MlC_normal.jpg', 'profile_image_url_https': 'https://pbs.twimg.com/profile_images/1456396286144307204/8SW-1MlC_normal.jpg', 'profile_link_color': '1DA1F2', 'profile_sidebar_border_color': 'C0DEED', 'profile_sidebar_fill_color': 'DDEEF6', 'profile_text_color': '333333', 'profile_use_background_image': True, 'has_extended_profile': True, 'default_profile': True, 'default_profile_image': False, 'following': False, 'follow_request_sent': False, 'notifications': False, 'translator_type': 'none', 'withheld_in_countries': []}, 'geo': None, 'coordinates': None, 'place': None, 'contributors': None, 'is_quote_status': False, 'retweet_count': 0, 'favorite_count': 0, 'favorited': False, 'retweeted': False, 'possibly_sensitive': False, 'lang': 'en'}

      await ctx.reply('**Created alert:**\n\n' + DISCORD_ALERT_FORMAT.format(
        'role_id_removed',
        twitch_channel.title,
        twitch_channel.game_name,
        BROADCASTER_CHANNEL
      ))

  async def tweet_command(ctx: AllContext, *args):
    raw = ctx.system_content.split('```')[1:-1]
    if ctx.is_mod and len(raw):
      status = raw[0].split('\n', 1)[-1]
      response = await twitter_bot.api.statuses.update.post(status=status)
      await ctx.reply('Sent tweet!')

  async def daily_command(ctx: AllContext, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    if (await is_live()):
      timestamp_key = f'daily_ts:{ctx.user_id}'
      now = time.time()
      subbed = await ctx.check_sub()

      # if 12 hours have passed since the last daily claim
      if now >= (timestamp := data.get(timestamp_key, 0)) + (60 * 60 * 12):
        data[timestamp_key] = now
        reward = random.randint(10, 100 if subbed else 50)
        bal_key = f'bal:{ctx.user_id}'
        bal = data[bal_key] = data.get(bal_key, 0) + reward
        if timestamp == 0:
          data['bal:sorted'] = list(sorted(data['bal:sorted'] + [str(ctx.user_id)], key=lambda u: data.get(f'bal:{u}', 0), reverse=True))
        await data.save()
        emoji = data['currency_emoji']
        await ctx.reply(f'Thanks for claiming your daily! Got {reward}{emoji} {" (sub bonus)" if subbed else ""}, Total: {bal}{emoji}')
      else:
        await ctx.reply('You have already claimed a daily in the last 12 hours! Try again later.')
    else:
      await ctx.reply(f'Since {BROADCASTER_CHANNEL} is not live, the daily command cannot be used.')

  async def lb_command(ctx: AllContext, *args):
    channels = await asyncio.gather(*(twitch_bot.fetch_channel(i) for i in data.get('bal:sorted', [])[:10]))
    names = (c.user.name for c in channels)
    result = ', '.join(f'{i}. {n}' for i, n in enumerate(names, start=1))
    await ctx.reply(f'{data.get("currency_emoji")} leaderboard: {result}')

  async def bal_command(ctx: AllContext, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    bal_key = f'bal:{ctx.user_id}'
    emoji = data['currency_emoji']
    await ctx.reply(f'You have {data.get(bal_key, 0)}{emoji}')

  async def buybox_command(ctx: AllContext, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    bal_key = f'bal:{ctx.user_id}'
    if (bal := data.get(bal_key, 0)) >= 50:
      box = await create_loot_box(ctx)
      inv_key = f'boxes:{ctx.user_id}'
      try:
        data[inv_key].append(box)
      except KeyError:
        data[inv_key] = [box]
      data[bal_key] = bal - 50
      await data.save()
      emoji = data['currency_emoji']
      await ctx.reply(f'Obtained {box["rarity"]} {box["name"]}! Paid 50{emoji}')
    else:
      await ctx.reply('Insufficient flowers.')

  async def boxes_command(ctx: AllContext, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    if (boxes := data.get(f'boxes:{ctx.user_id}')) is None:
      return await ctx.reply('Your inventory is empty. :(')

    quantities = {
      RARITY_COMMON: 0,
      RARITY_UNCOMMON: 0,
      RARITY_RARE: 0,
      RARITY_MYTHIC: 0,
      RARITY_LEGENDARY: 0
    }

    for box in boxes:
      quantities[box['rarity']] += 1

    boxes_str = '\n'.join(f'{rarity} ({quantity})' for rarity, quantity in quantities.items() if quantity)
    await ctx.reply(f'Loot boxes: {boxes_str}')

  async def inv_command(ctx: AllContext, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    if (items := data.get(f'inv:{ctx.user_id}')) is None:
      return await ctx.reply('Your inventory is empty. :(')

    items = (f'{x}. {item["rarity"]} {item["name"]}' for x, item in enumerate(items, 0))
    await ctx.reply(INVENTORY_TEMPLATE.format('\n'.join(items)))

  async def item_command(ctx: AllContext, *args):
    await ctx.reply('Under construction! wait patiently..... or not idc')

  async def usebox_command(ctx: AllContext, *args):
    await ctx.reply('Under construction! wait patiently..... or not idc')

  async def sub_command(ctx: AllContext, *args):
    if await ctx.check_sub():
      await ctx.reply('uwu yes you are a sub')
    else:
      await ctx.reply('wtf why aren\'t you subbed????')

  # async def test_command(ctx: AllContext, *args):
  #   if ctx.user_id is not None:
  #     broadcaster_response = await ctx.twitch_bot.fetch_users(names=[BROADCASTER_CHANNEL])
  #     if len(broadcaster_response) > 0:
  #       print(await broadcaster_response[0].fetch_subscriptions(TWITCH_TOKEN, userids=[ctx.user_id]))


  add_commands(
    edit_command,
    alert_command,
    tweet_command,
    status_command,
    link_command,
    code_command,
    ddnet_command,
    discord_command,
    donate_command,
    faq_command,
    mc_command,
    ip_command,
    survey_command,
    tournament_command,
    tourney_command,
    lcsg_command,
    twitter_command,
    youtube_command,
    daily_command,
    lb_command,
    bal_command,
    buybox_command,
    boxes_command,
    inv_command,
    item_command,
    usebox_command,
    sub_command
  )

  await discord_bot.login(DISCORD_TOKEN)
  await asyncio.gather(*(bot.connect() for bot in [twitch_bot, discord_bot]))

if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    exit()
