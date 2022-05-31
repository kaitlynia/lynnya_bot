import asyncio
import json
import traceback

import websockets
from websockets.client import WebSocketClientProtocol

import constants
from bot_data import BotData
from context import Context, PetalContext
from discord_bot import DiscordBot
from twitch_bot import TwitchBot


class PetalBot:
  log_as = constants.LOG_PETAL_AS

  def __init__(self, data: BotData, token: str, name: str, twitch_bot: TwitchBot, discord_bot: DiscordBot):
    self.prefix = data[constants.PETAL_PREFIX_KEY]
    self.data = data
    self.token = token
    self.name = name
    self.twitch_bot = twitch_bot
    self.discord_bot = discord_bot
    self.ws: WebSocketClientProtocol = None
    self.commands = {}

  async def send(self, **data):
    await self.ws.send(json.dumps(data))

  async def login(self):
    self.ws: WebSocketClientProtocol = await websockets.connect(constants.PETAL_SERVER)
    await self.send(type = 'auth-token', name = self.name, token = self.token)

    async def event_message(message):
      if (message.echo or not message.content or message.author.name == 'nightbot'):
        return
      elif message.content.startswith(self.data[constants.TWITCH_PREFIX_KEY]):
        return await self.twitch_bot.handle_commands(message)

      await asyncio.gather(
        self.discord_bot.get_channel(constants.DISCORD_BRIDGE_CHANNEL_ID).send(
          f'<:twitch:912098198934409248> {message.author.name}: {message.content}'
        ),
        self.ws.send(json.dumps({
          'type': 'message',
          'body': f'[twitch] {message.author.name}: {message.content}'
        }))
      )
    self.twitch_bot.event_message = event_message

    async def on_message(message):
      if message.channel.id != constants.DISCORD_BRIDGE_CHANNEL_ID or\
        message.author.bot or not message.clean_content:
        return
      elif message.system_content.startswith(self.data[constants.DISCORD_PREFIX_KEY]):
        return await self.discord_bot.process_commands(message)

      await asyncio.gather(
        self.twitch_bot.get_channel(constants.BROADCASTER_CHANNEL).send(
          f'🔵 {message.author.display_name}: {message.clean_content}'
        ),
        self.ws.send(json.dumps({
        'type': 'message',
        'body': f'[discord] {message.author.display_name}: {message.clean_content}'
        }))
      )
    self.discord_bot.on_message = on_message

    async for message in self.ws:
      payload = json.loads(message)
      name, body = payload.get('name'), payload.get('body')
      if payload.get('type') == 'message' and name != self.name:
        if body.startswith(self.data[constants.PETAL_PREFIX_KEY]):
          args = body.split()
          try:
            coro = self.commands.get(args[0].split(self.data[constants.PETAL_PREFIX_KEY], 1)[-1])
            if coro is not None:
              await coro(Context(self.twitch_bot, self.discord_bot, self, PetalContext(self.ws, name, body), self.data), *args[1:])
          except:
            print(traceback.format_exc())
        else:
          bridge_str = f'{constants.PETAL_EMOJI} {name or "anon"}: {body}'
          await asyncio.gather(
            self.twitch_bot.get_channel(constants.BROADCASTER_CHANNEL).send(bridge_str),
            self.discord_bot.get_channel(constants.DISCORD_BRIDGE_CHANNEL_ID).send(bridge_str)
          )

  def add_command(self, name, coro):
    self.commands[name] = coro
