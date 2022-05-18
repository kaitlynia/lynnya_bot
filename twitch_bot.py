from twitchio.errors import AuthenticationError
from twitchio.ext.commands import Bot
from twitchio.ext.commands import CommandNotFound

import constants

from bot_data import BotData
from loggable import Loggable


class TwitchBot(Bot, Loggable):
  log_as = constants.LOG_TWITCH_AS

  def __init__(self, token: str, data: BotData):
    super().__init__(
      token=token,
      prefix=data[constants.TWITCH_PREFIX_KEY],
      initial_channels=[constants.BROADCASTER_CHANNEL]
    )
    self.data = data

  async def connect(self):
    self.log_info(constants.LOGIN_ATTEMPT_MESSAGE)
    try:
      await super().connect()
      self.log_info(constants.LOGIN_SUCCESS_MESSAGE)
    except AuthenticationError:
      self.log_error(constants.LOGIN_AUTH_ERROR_MESSAGE)
    except Exception as exc:
      self.log_error(constants.LOGIN_ERROR_MESSAGE)
      raise exc

  async def event_command_error(self, ctx, error):
    if isinstance(error, CommandNotFound):
      return
    raise error

  async def event_ready(self):
    self.log_done('ready')
