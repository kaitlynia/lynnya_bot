from discord.ext.commands import Bot as DiscordBot
from discord.ext.commands import Context as DiscordContext
from twitchio.ext.commands import Bot as TwitchBot
from twitchio.ext.commands import Context as TwitchContext

import constants
from bot_data import BotData


class Context:
  def __init__(self, discord_bot: DiscordBot, twitch_bot: TwitchBot, ctx, data: BotData):
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
    if self.source_type is DiscordContext:
      self.is_mod = ctx.author.permissions_in(ctx.bot.get_channel(constants.DISCORD_STAFF_CHANNEL_ID)).view_channel

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
          return any(role.id == constants.DISCORD_SUBSCRIBER_ROLE_ID for role in ctx.author.roles)

        self.check_sub = check_sub

      else:
        async def check_sub():
          return any(role.id == constants.DISCORD_SUBSCRIBER_ROLE_ID for role in ctx.author.roles)

        self.check_sub = check_sub

      async def __reply(content: str):
        formatted = content.replace('/>', '>')
        await ctx.reply(formatted)

      self.reply = __reply

    elif self.source_type is TwitchContext:
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
    if self.source_type is DiscordContext:
      return self.data[constants.DISCORD_PREFIX_KEY]
    elif self.source_type is TwitchContext:
      return self.data[constants.TWITCH_PREFIX_KEY]
    else:
      raise RuntimeError(f'unknown prefix for source type: {type(self.source_type)}')
