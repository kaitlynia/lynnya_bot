import asyncio
import json

import websockets
from websockets.client import WebSocketClientProtocol

import constants

from bot_data import BotData
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

  async def send(self, **data):
    await self.ws.send(json.dumps(data))

  async def login(self):
    self.ws: WebSocketClientProtocol = await websockets.connect(constants.PETAL_SERVER)
    await self.send(type = 'auth-token', name = self.name, token = self.token)

    # async def event_message(message):
    #   if (message.echo or not message.content): return
    #   await self.ws.send(json.dumps({
    #     'type': 'message',
    #     'body': f'[twitch] {message.author.name}: {message.content}'
    #   }))
    # self.twitch_bot.event_message = event_message

    # async def on_message(message):
    #   self.discord_bot.command
    #   if message.channel.id != DISCORD_BRIDGE_CHANNEL_ID or message.author.bot or not message.clean_content:
    #     return
    #   await self.ws.send(json.dumps({
    #     'type': 'message',
    #     'body': f'[discord] {message.author.display_name}: {message.clean_content}'
    #   }))
    # self.discord_bot.on_message = on_message

    async for message in self.ws:
      payload = json.loads(message)
      if payload.get('type') == 'message' and payload.get('name') != constants.PETAL_NAME:
        send_str = f'{constants.PETAL_EMOJI} {payload.get("name", "anon")}: {payload.get("body")}'
        await asyncio.gather(
          self.twitch_bot.get_channel(constants.BROADCASTER_CHANNEL).send(send_str),
          self.discord_bot.get_channel(constants.DISCORD_BRIDGE_CHANNEL_ID).send(send_str)
        )