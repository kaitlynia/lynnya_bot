from discord.errors import LoginFailure
from discord.ext.commands import Bot
from discord.ext.commands import CommandNotFound

import constants

from bot_data import BotData
from loggable import Loggable


class DiscordBot(Bot, Loggable):
  log_as = constants.LOG_DISCORD_AS

  def __init__(self, data: BotData):
    super().__init__(command_prefix=data[constants.DISCORD_PREFIX_KEY])
    self.data = data

  async def login(self, token: str):
    self.log_info(constants.LOGIN_ATTEMPT_MESSAGE)
    try:
      await super().login(token)
      self.log_done(constants.LOGIN_SUCCESS_MESSAGE)
    except LoginFailure:
      self.log_error(constants.LOGIN_AUTH_ERROR_MESSAGE)
    except Exception as exc:
      self.log_error(constants.LOGIN_ERROR_MESSAGE)
      raise exc

  async def on_command_error(self, ctx, error):
    if isinstance(error, CommandNotFound):
      return
    raise error.original

  async def on_ready(self):
    self.log_done('ready')
