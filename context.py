import json
import time

from discord.ext.commands import Bot as DiscordBot
from discord.ext.commands import Context as DiscordContext
from twitchio.ext.commands import Bot as TwitchBot
from twitchio.ext.commands import Context as TwitchContext
from websockets.client import WebSocketClientProtocol

import constants
from bot_data import BotData


class Context:
  def __init__(self, twitch_bot: TwitchBot, discord_bot: DiscordBot, petal_bot, ctx, data: BotData):
    self.twitch_bot = twitch_bot
    self.discord_bot = discord_bot
    self.petal_bot = petal_bot
    self.source_ctx = ctx
    self.data = data

    self.source_id = None
    self.source_type = type(ctx)
    self.system_content = None
    self.clean_content = None
    self.is_mod = None
    self.is_subscriber = None

    self.user_id = None
    self.reply = None

    if self.source_type is TwitchContext:
      self.source_id = int(ctx.author.id)
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

    # context check to populate user_id
    elif self.source_type is DiscordContext:
      self.source_id = ctx.author.id
      self.is_mod = ctx.author.permissions_in(ctx.bot.get_channel(constants.DISCORD_STAFF_CHANNEL_ID)).view_channel

      self.system_content = ctx.message.system_content
      self.clean_content = ctx.message.clean_content
      self.timestamp = ctx.message.created_at.timestamp()

      discord_to_twitch_key = f'discord:{self.source_id}'
      if discord_to_twitch_key in data:
        self.user_id = data[discord_to_twitch_key]

      async def check_sub():
        return any(role.id == constants.DISCORD_SUBSCRIBER_ROLE_ID for role in ctx.author.roles)

      self.check_sub = check_sub

      async def __reply(content: str):
        formatted = content.replace('/>', '>')
        await ctx.reply(formatted)

      self.reply = __reply

    # raw dict payloads are received from Petal
    elif self.source_type is PetalContext:
      self.source_id = ctx.author
      self.is_mod = False

      self.system_content = ctx.body
      self.clean_content = ctx.body
      self.timestamp = time.time()

      petal_to_twitch_key = f'petal:{self.source_id}'
      if petal_to_twitch_key in data:
        self.user_id = data[petal_to_twitch_key]

      async def check_sub():
        if self.user_id is not None:
          chatter_name = (await self.twitch_bot.fetch_channel(str(self.user_id))).user.channel.name
          chatter = self.twitch_bot.get_channel(constants.BROADCASTER_CHANNEL).get_chatter(chatter_name)
          if chatter is None:
            return None
          else:
            return chatter.is_subscriber

      self.check_sub = check_sub

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
    if self.source_type is DiscordContext:
      return self.data[constants.DISCORD_PREFIX_KEY]
    elif self.source_type is TwitchContext:
      return self.data[constants.TWITCH_PREFIX_KEY]
    else:
      raise RuntimeError(f'unknown prefix for source type: {type(self.source_type)}')

class PetalContext:
  def __init__(self, ws: WebSocketClientProtocol, author: str, body: str):
    self.ws = ws
    self.author = author
    self.body = body

  async def reply(self, body: str):
    await self.ws.send(json.dumps({
      'type': 'message',
      'body': body
    }))
