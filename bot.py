import asyncio
import json
import random
import re
import time

from discord.ext import commands as discord
from peony import PeonyClient as TwitterBot
from twitchio import Message as TwitchMessage
from twitchio.ext import commands as twitch

VERSION='0.2.0'

import constants
import util

from bot_data import BotData
from context import Context
from discord_bot import DiscordBot
from petal_bot import PetalBot
from twitch_bot import TwitchBot

# load loot box items table
with open('items.json') as f:
  LOOT_BOX_ITEMS = json.load(f)

# load English word list TODO: extend this to include common tokens used in chats (uwu, IRL, etc.)
with open('words.txt') as f:
  ENGLISH_WORDS = set(f.read().lower().split())

async def main():
  util.print_box(f'{constants.BOT_NAME} v{VERSION}')

  data = BotData(constants.DATA_PATH)
  await data.load()

  twitch_bot = TwitchBot(constants.TWITCH_TOKEN, data)
  discord_bot = DiscordBot(data)
  twitter_bot = TwitterBot(
    constants.TWITTER_KEY,
    constants.TWITTER_SECRET,
    constants.TWITTER_ACCESS_TOKEN,
    constants.TWITTER_ACCESS_TOKEN_SECRET
  )
  petal_bot = PetalBot(data, constants.PETAL_TOKEN, constants.PETAL_NAME, twitch_bot, discord_bot)

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

    # remove symbols, .lower(), then tokenize
    tokens = re.sub(r'[^\w+]', ' ', tokens_str).lower().split()

    # remove duplicate tokens, then remove tokens that are not known to be English words
    words = list(t for t in set(tokens) if t in ENGLISH_WORDS)
    num_words = len(words)

    # find the average of averages for each word's levenshtein distances to other words in the message
    # NOTE: this is a SOMEWHAT accurate way of determining valuable/conversational messages, but it is not ideal
    words_score = sum(sum(util.leven(word, w) for w in words) / num_words for word in words) / num_words if num_words else 0

    # calculate total score with the emote score combined
    total_score = int(words_score + num_emotes ** constants.EMOTE_VALUE_EXPONENT)

    partial_bal_key = f'partial_bal:{message.author.id}'
    partial_bal = data[partial_bal_key] = data.get(partial_bal_key, 0) + total_score

    if partial_bal >= constants.PARTIAL_BAL_PER_BAL:
      data[partial_bal_key] = partial_bal - constants.PARTIAL_BAL_PER_BAL
      bal_key = f'bal:{message.author.id}'
      data[bal_key] = data.get(bal_key, 0) + 1

    await data.save()

  @discord_bot.event
  async def on_voice_state_update(member, before, after):
    if member.id == constants.DISCORD_BROADCASTER_ID:
      if before.channel is not None and \
        before.channel.id == constants.DISCORD_LIVE_VOICE_CHANNEL_ID and \
        (after.channel is None or after.channel.id != constants.DISCORD_LIVE_VOICE_CHANNEL_ID):

        reason = 'broadcaster left LIVE channel'
        guild = before.channel.guild
        live_voice_channel = before.channel
        closed_voice_channel = guild.get_channel(constants.DISCORD_CLOSED_VOICE_CHANNEL_ID)

        discord_bot.log_info('disabling LIVE channel for members')
        await live_voice_channel.set_permissions(guild.default_role, view_channel=False, connect=False, reason=reason)
        discord_bot.log_done('disabled LIVE')
        if (num_members := len(live_voice_channel.members)):
          discord_bot.log_info(f'moving {num_members} members')
          move_gen = (m.move_to(closed_voice_channel, reason=reason) for m in live_voice_channel.members)
          await asyncio.gather(*move_gen)
          discord_bot.log_done('moved members')

      elif after.channel is not None and \
        after.channel.id == constants.DISCORD_LIVE_VOICE_CHANNEL_ID and \
        (before.channel is None or before.channel.id != constants.DISCORD_LIVE_VOICE_CHANNEL_ID):

        reason = 'broadcaster joined LIVE channel'
        live_voice_channel = after.channel

        discord_bot.log_info('enabling LIVE channel for members')
        await live_voice_channel.set_permissions(live_voice_channel.guild.default_role, view_channel=True, connect=False)
        discord_bot.log_done('enabled LIVE')

  @discord_bot.check
  async def __limit_commands_to_channels(ctx: discord.Context):
    return ctx.guild is not None and ctx.channel.id in constants.DISCORD_CHANNEL_IDS

  async def is_live(channel_name: str = constants.BROADCASTER_CHANNEL):
    return bool(await twitch_bot.fetch_streams(user_logins=[channel_name]))

  async def reply_not_linked(ctx: Context):
    return await ctx.reply(f'This command requires a linked Discord account. Use {data[constants.DISCORD_PREFIX_KEY]}link in Discord to link your accounts.')

  def add_command(coro, name=None):
    @twitch_bot.command(name=name or coro.__name__.replace('_command', ''))
    async def __twitch_command(ctx, *args):
      await coro(Context(discord_bot, twitch_bot, ctx, data), *args)

    @discord_bot.command(name=name or coro.__name__.replace('_command', ''))
    async def __discord_command(ctx, *args):
      await coro(Context(discord_bot, twitch_bot, ctx, data), *args)

  def add_commands(*coros):
    for coro in coros:
      add_command(coro)

  async def basic_command(ctx: Context, key: str, label: str, intro: str, *args, unavailable='n/a'):
    if ctx.is_mod and len(args):
      data[key] = ' '.join(args)
      await data.save()
      await ctx.reply(f'{label} updated!')
    else:
      await ctx.reply(f'{intro}{data.get(key, unavailable)}')


  #################
  ### RPG LOGIC ###
  #################

  async def create_loot_box(ctx: Context):
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
      box['rarity'] = constants.RARITY_LEGENDARY
    elif roll < 0.05:
      box['rarity'] = constants.RARITY_MYTHIC
    elif roll < 0.15:
      box['rarity'] = constants.RARITY_RARE
    elif roll < 0.4:
      box['rarity'] = constants.RARITY_UNCOMMON
    else:
      box['rarity'] = constants.RARITY_COMMON

    return box

  # def resolve_box_rarity(rarity_str: str):
  #   rarity_str = rarity_str.lower()
  #   for rarity in ['common', 'uncommon', 'rare', 'mythic', 'legendary']:
  #     if rarity.startswith(rarity_str):
  #       return rarity.capitalize()
  #   return None

  # def items_from_box(box):
  #   pass


  ################
  ### COMMANDS ###
  ################

  async def code_command(ctx: Context, *args):
    await basic_command(ctx, 'info:lobby', 'Lobby code', 'Lobby code: ', *args)
  async def ddnet_command(ctx: Context, *args):
    await basic_command(ctx, 'info:ddnet', 'DDNet profile', 'DDNet player profile: ', *args)
  async def discord_command(ctx: Context, *args):
    await basic_command(ctx, 'info:discord', 'Discord server', 'Join lynnya\'s lair! ', *args)
  async def donate_command(ctx: Context, *args):
    await basic_command(ctx, 'info:donate', 'Donate link', 'Donate to lynnya: ', *args)
  async def faq_command(ctx: Context,  *args):
    await basic_command(ctx, 'info:faq', 'FAQ link', 'FAQ: ', *args)
  async def mc_command(ctx: Context, *args):
    await basic_command(ctx, 'info:mc', 'Minecraft server info', 'Join lynnSMP! ', *args)
  async def ip_command(ctx: Context, *args):
    await mc_command(ctx, *args)
  async def survey_command(ctx: Context, *args):
    await basic_command(ctx, 'info:survey', 'Survey info', 'Please fill out this survey! ', *args)
  async def tournament_command(ctx: Context, *args):
    await basic_command(ctx, 'info:tournament', 'Tournament info', 'Tournament rules: ', *args)
  async def tourney_command(ctx: Context, *args):
    await tournament_command(ctx, *args)
  async def lcsg_command(ctx: Context, *args):
    await tournament_command(ctx, *args)
  async def twitter_command(ctx: Context, *args):
    await basic_command(ctx, 'info:twitter', 'Twitter link', 'Follow for stream notifications, updates, and bad cat puns: ', *args)
  async def youtube_command(ctx: Context, *args):
    await basic_command(ctx, 'info:youtube', 'YouTube link', 'Subscribe to lynnya on YouTube: ', *args)

  async def edit_command(ctx: Context, *args):
    if ctx.is_mod:
      if len(args) < 2:
        return await ctx.reply('Missing info message argument.')
      name = args[0]
      data[f'info:{name}'] = ' '.join(args[1:])
      await ctx.reply(f'Info for "{name}" updated!')

  async def link_command(ctx: Context, *code):
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
        await (await discord_bot.fetch_user(ctx.source_id)).send(f'Use `{data["prefix:twitch"]}link {code}` in Twitch chat (<https://twitch.tv/{constants.BROADCASTER_CHANNEL}/>) to link your account.')
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
        await ctx.reply(f'Missing code argument. Use {data[constants.DISCORD_PREFIX_KEY]}link in Discord to link your accounts.')

  async def status_command(ctx: Context, *args):
    twitch_channel = await twitch_bot.fetch_channel(constants.BROADCASTER_CHANNEL)
    online = await is_live()
    status = '**Online**' if online else 'Offline'
    stream_link = f'https://twitch.tv/{constants.BROADCASTER_CHANNEL}'
    stream_link_embedded = stream_link if online else f'<{stream_link}/>'
    await ctx.reply(f'''{status}
**Title:** {twitch_channel.title}
**Game:** ({twitch_channel.game_name})
**Stream:** {stream_link_embedded}''')

  async def alert_command(ctx: Context, *args):
    if ctx.is_mod:
      twitch_channel = await twitch_bot.fetch_channel(constants.BROADCASTER_CHANNEL)
      alerts_channel = discord_bot.get_channel(constants.DISCORD_ALERTS_CHANNEL_ID)

      await alerts_channel.send(constants.DISCORD_ALERT_FORMAT.format(
        constants.DISCORD_ALERTS_ROLE_ID,
        twitch_channel.title,
        twitch_channel.game_name,
        constants.BROADCASTER_CHANNEL
      ))

      response = await twitter_bot.api.statuses.update.post(status=constants.TWITTER_ALERT_FORMAT.format(
        twitch_channel.title,
        twitch_channel.game_name,
        constants.BROADCASTER_CHANNEL
      ))

      await ctx.reply('**Created alert:**\n\n' + constants.DISCORD_ALERT_FORMAT.format(
        'role_id_removed',
        twitch_channel.title,
        twitch_channel.game_name,
        constants.BROADCASTER_CHANNEL
      ))

  async def tweet_command(ctx: Context, *args):
    raw = ctx.system_content.split('```')[1:-1]
    if ctx.is_mod and len(raw):
      status = raw[0].split('\n', 1)[-1]
      response = await twitter_bot.api.statuses.update.post(status=status)
      await ctx.reply('Sent tweet!')

  async def daily_command(ctx: Context, *args):
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
      await ctx.reply(f'Since {constants.BROADCASTER_CHANNEL} is not live, the daily command cannot be used.')

  async def lb_command(ctx: Context, *args):
    channels = await asyncio.gather(*(twitch_bot.fetch_channel(i) for i in data.get('bal:sorted', [])[:10]))
    names = (c.user.name for c in channels)
    result = ', '.join(f'{i}. {n}' for i, n in enumerate(names, start=1))
    await ctx.reply(f'{data.get("currency_emoji")} leaderboard: {result}')

  async def bal_command(ctx: Context, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    bal_key = f'bal:{ctx.user_id}'
    emoji = data['currency_emoji']
    await ctx.reply(f'You have {data.get(bal_key, 0)}{emoji}')

  async def buybox_command(ctx: Context, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    bal_key = f'bal:{ctx.user_id}'
    quantity = 1

    if (len(args) > 0):
      if (num_argument := args[0]) == 'all':
        quantity = data.get(bal_key, 0) // 50
        if quantity < 1:
          return await ctx.reply('Insufficient flowers.')
      else:
        try:
          quantity = int(num_argument)
          if quantity < 1:
            return await ctx.reply('Invalid number of boxes.')
        except ValueError:
          return await ctx.reply('Invalid number of boxes.')

    if (bal := data.get(bal_key, 0)) >= 50 * quantity:
      boxes = [await create_loot_box(ctx)]
      boxes_key = f'boxes:{ctx.user_id}'
      try:
        data[boxes_key].append(boxes[0])
      except KeyError:
        data[boxes_key] = [boxes[0]]
      for _ in range(quantity - 1):
        boxes.append(await create_loot_box(ctx))
        data[boxes_key].append(boxes[-1])

      data[bal_key] = bal - (50 * quantity)
      await data.save()
      emoji = data['currency_emoji']

      quantities = {
        constants.RARITY_COMMON: 0,
        constants.RARITY_UNCOMMON: 0,
        constants.RARITY_RARE: 0,
        constants.RARITY_MYTHIC: 0,
        constants.RARITY_LEGENDARY: 0
      }

      for box in boxes:
        quantities[box['rarity']] += 1

      boxes_str = '\n' + '\n'.join(f'{rarity} ({quantity})' for rarity, quantity in quantities.items() if quantity) + '\n\n'

      await ctx.reply(f'Obtained: {boxes_str}Paid {50 * quantity}{emoji}')
    else:
      await ctx.reply('Insufficient flowers.')

  async def boxes_command(ctx: Context, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    if not (boxes := data.get(f'boxes:{ctx.user_id}')):
      return await ctx.reply('Your inventory is empty. :(')

    quantities = {
      constants.RARITY_COMMON: 0,
      constants.RARITY_UNCOMMON: 0,
      constants.RARITY_RARE: 0,
      constants.RARITY_MYTHIC: 0,
      constants.RARITY_LEGENDARY: 0
    }

    for box in boxes:
      quantities[box['rarity']] += 1

    boxes_str = '\n' + '\n'.join(f'{rarity} ({quantity})' for rarity, quantity in quantities.items() if quantity)
    await ctx.reply(f'Loot boxes: {boxes_str}')

  async def inv_command(ctx: Context, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    if not (items := data.get(f'inv:{ctx.user_id}')):
      return await ctx.reply('Your inventory is empty. :(')

    items = (f'{x}. {item["rarity"]} {item["name"]}  [+{item["reforge_stat"]} {item["stat_type"]}]' for x, item in enumerate(items, 0))
    await ctx.reply(constants.INVENTORY_TEMPLATE.format('\n'.join(items)))

  async def item_command(ctx: Context, *args):
    await ctx.reply('Under construction! wait patiently..... or not idc')

  # async def usebox_command(ctx: Context, *args):
  #   if ctx.user_id is None:
  #     return await reply_not_linked(ctx)

  #   boxes_key = f'boxes:{ctx.user_id}'
  #   if not (boxes := data.get(boxes_key)):
  #     return await ctx.reply('Your inventory is empty. :(')

  #   box_to_open = None

  #   if len(args) > 0:
  #     rarity = resolve_box_rarity(args[0])
  #     if rarity is None:
  #       return await ctx.reply('Invalid box rarity.')
  #     for box in boxes:
  #       if box['rarity'] == rarity:
  #         box_to_open = box
  #         break
  #     if box_to_open is None:
  #       return await ctx.reply('You do not have any boxes of that rarity.')

  #   else:
  #     # find most recent box
  #     box_to_open = sorted(boxes, key=lambda b: b['timestamp'])[-1]

  #   boxes.remove(box_to_open)
  #   data[boxes_key] = boxes

  #   items = util.items_from_box(box_to_open)
  #   inv_key = f'inv:{ctx.user_id}'
  #   try:
  #     data[inv_key] += [*items]
  #   except KeyError:
  #     data[inv_key] = [*items]
  #   data.save()

  #   items_str = '\n' + '\n'.join(f'{item["rarity"]} {item["name"]} [+{item["rarity_stat"]} {item["stat_type"]}]' for item in items) + '\n\n'

  #   await ctx.reply(f'Obtained: {items_str}')

  async def sub_command(ctx: Context, *args):
    if await ctx.check_sub():
      await ctx.reply('uwu yes you are a sub')
    else:
      await ctx.reply('wtf why aren\'t you subbed????')

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
    # usebox_command,
    sub_command
  )

  await discord_bot.login(constants.DISCORD_TOKEN)
  asyncio.create_task(petal_bot.login())
  await asyncio.gather(*(bot.connect() for bot in [twitch_bot, discord_bot]))

if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    exit()
