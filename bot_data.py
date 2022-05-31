import json

from aiofiles import open as aiopen
from aiofiles.threadpool.text import AsyncTextIOWrapper

import constants
from loggable import Loggable


class BotData(dict, Loggable):
  log_as = constants.LOG_DATA_AS
  defaults = {
    constants.TWITCH_PREFIX_KEY: constants.DEFAULT_PREFIX,
    constants.DISCORD_PREFIX_KEY: constants.DEFAULT_PREFIX,
    constants.PETAL_PREFIX_KEY: constants.DEFAULT_PREFIX,
    'currency_emoji': constants.DEFAULT_CURRENCY_EMOJI,
    'bal:sorted': [],
    'daily_reminders_list': []
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

  async def save(self, reason=None):
    self.log_info(f'saving data ({reason if reason else "unspecified reason"})')

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
