import asyncio
import json
import random
import re
import time

from aiofiles import open as aiopen
from discord import RawReactionActionEvent as DiscordRawReactionActionEvent
from discord.ext import commands as discord
from peony import PeonyClient as TwitterBot
from twitchio import Message as TwitchMessage
from twitchio.ext import commands as twitch

VERSION='0.2.5'

import constants
import util
from bot_data import BotData
from context import Context
from discord_bot import DiscordBot
from petal_bot import PetalBot, PetalContext
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

    await data.save('chat currency award')

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
        await live_voice_channel.set_permissions(live_voice_channel.guild.default_role, view_channel=False, connect=False, reason=reason)
        discord_bot.log_done('disabled LIVE channel')
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
        await live_voice_channel.set_permissions(live_voice_channel.guild.default_role, view_channel=True, connect=False, reason=reason)
        discord_bot.log_done('enabled LIVE channel')

  async def handle_reaction(reaction: DiscordRawReactionActionEvent):
    # TODO: add logging
    if reaction.channel_id == constants.DISCORD_REACTION_ROLES_CHANNEL_ID:
      role = None

      if reaction.event_type == 'REACTION_ADD':
        member = reaction.member
      else:
        member = await (discord_bot.get_guild(reaction.guild_id)).fetch_member(reaction.user_id)

      if reaction.emoji.name == constants.DISCORD_REACTION_ROLES_ALERTS_EMOJI:
        role = member.guild.get_role(constants.DISCORD_ALERTS_ROLE_ID)
      elif reaction.emoji.name == constants.DISCORD_REACTION_ROLES_RESCUE_EMOJI:
        role = member.guild.get_role(constants.DISCORD_TIMER_ALERTS_ROLE_ID)
      elif reaction.event_type == 'REACTION_ADD':
        await (
          await (
            discord_bot.get_channel(reaction.channel_id)
          ).fetch_message(reaction.message_id)
        ).remove_reaction(reaction.emoji, member)

      if role is not None:
        if reaction.event_type == 'REACTION_ADD':
          await member.add_roles(role)
        else:
          await member.remove_roles(role)

  @discord_bot.event
  async def on_member_join(member):
    # TODO: add logging
    await member.add_roles(member.guild.get_role(constants.DISCORD_ALERTS_ROLE_ID))

  @discord_bot.event
  async def on_raw_reaction_add(payload):
    await handle_reaction(payload)

  @discord_bot.event
  async def on_raw_reaction_remove(payload):
    await handle_reaction(payload)

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
      await coro(Context(twitch_bot, discord_bot, petal_bot, ctx, data), *args)

    @discord_bot.command(name=name or coro.__name__.replace('_command', ''))
    async def __discord_command(ctx, *args):
      await coro(Context(twitch_bot, discord_bot, petal_bot, ctx, data), *args)

    petal_bot.add_command(name or coro.__name__.replace('_command', ''), coro)

  def add_commands(*coros):
    for coro in coros:
      add_command(coro)

  async def basic_command(ctx: Context, key: str, label: str, intro: str, *args, unavailable='n/a'):
    if ctx.is_mod and len(args):
      data[key] = ' '.join(args)
      await data.save('basic command edited')
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
      if not len(code):
        return await ctx.reply('Twitch name required.')
      code = code[0]
      data[f'link:discord_{ctx.source_id}'] = code.lower()
      await data.save(f'Twitch link for {code} started (discord_{ctx.source_id})')
      await ctx.reply(f'Link started for `{code}`. Use `!link discord_{ctx.source_id}` in Twitch using that account to finish linking.')
    elif ctx.source_type is twitch.Context:
      if not len(code):
        return await ctx.reply('Link code required. Use `!link TwitchName` in Discord/Petal to start linking.')
      code = code[0]
      try:
        link_type, link_id = tuple(code.split('_', 1))
        if link_type == 'discord':
          if len(link_id) != 18 or not link_id.isdigit():
            raise ValueError
        elif link_type != 'petal':
          raise ValueError
      except ValueError:
        return await ctx.reply('Invalid link code. Use `!link TwitchName` in Discord/Petal to start linking.')

      code_key = f'link:{code}'
      if (twitch_name := data.get(code_key)) is None:
        return await ctx.reply('Invalid link code. Use `!link TwitchName` in Discord/Petal to start linking.')
      if ctx.source_ctx.author.name != twitch_name:
        return await ctx.reply('This link code was created for a different user. Use `!link TwitchName` in Discord/Petal to start linking.')
      del data[code_key]
      data[f'{link_type}:{link_id}'] = ctx.user_id
      await data.save(f'Link finished for {twitch_name} (Code: {code})')
      await ctx.reply(f'{link_type.capitalize()} account linked!')
    elif ctx.source_type is PetalContext:
      if not len(code):
        return await ctx.reply('Link code required. Use `!link TwitchName` in Discord/Petal to start linking.')
      code = code[0]
      data[f'link:petal_{ctx.source_id}'] = code.lower()
      await data.save(f'Twitch link for {code} started (petal_{ctx.source_id})')
      await ctx.reply(f'Link started for `{code}`. Use `!link petal_{ctx.source_id}` in Twitch using that account to finish linking.')

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
    # TODO: add logging
    if ctx.is_mod:
      twitch_channel = await twitch_bot.fetch_channel(constants.BROADCASTER_CHANNEL)
      alerts_channel = discord_bot.get_channel(constants.DISCORD_ALERTS_CHANNEL_ID)

      await alerts_channel.send(constants.DISCORD_ALERT_FORMAT.format(
        constants.DISCORD_ALERTS_ROLE_ID,
        twitch_channel.title,
        twitch_channel.game_name,
        constants.BROADCASTER_CHANNEL
      ))

      await twitter_bot.api.statuses.update.post(status=constants.TWITTER_ALERT_FORMAT.format(
        twitch_channel.title,
        twitch_channel.game_name,
        constants.BROADCASTER_CHANNEL
      ))

  async def tweet_command(ctx: Context, *args):
    # TODO: add logging
    raw = ctx.system_content.split('```')[1:-1]
    if ctx.is_mod and len(raw):
      status = raw[0].split('\n', 1)[-1]
      response = await twitter_bot.api.statuses.update.post(status=status)
      await ctx.reply('Sent tweet!')

  async def remind_command(ctx: Context, *args):
    if ctx.source_type is not discord.Context:
      return await ctx.reply('This command can only be used from Discord.')
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    data['daily_reminders_list'].append(ctx.source_id)
    await data.save('added Discord user to the daily reminders list')
    await ctx.reply(f'I will now send you {data[constants.DISCORD_PREFIX_KEY]}daily reminders! If you want to un-subscribe from daily reminders, use `{data[constants.DISCORD_PREFIX_KEY]}unremind`')

  async def unremind_command(ctx: Context, *args):
    if ctx.source_type is not discord.Context:
      return await ctx.reply('This command can only be used from Discord.')
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    data['daily_reminders_list'].remove(ctx.source_id)
    reminder_key = f'daily_reminder:{ctx.user_id}'
    if reminder_key in data:
      del data[reminder_key]
    await data.save('removed Discord user from the daily reminders list')
    await ctx.reply(f'I will not send you {data[constants.DISCORD_PREFIX_KEY]}daily reminders. If you want to re-subscribe, use `{data[constants.DISCORD_PREFIX_KEY]}remind`')

  async def daily_command(ctx: Context, *args):
    if ctx.user_id is None:
      return await reply_not_linked(ctx)
    if (await is_live()):
      timestamp_key = f'daily_ts:{ctx.user_id}'
      now = time.time()
      subbed = await ctx.check_sub()
      if subbed is None:
        return await ctx.reply('Daily claims require your sub status to ensure the correct payout. Make sure to chat at least once in Twitch chat so that the sub status can be determined.')

      # if 12 hours have passed since the last daily claim
      if now >= (time_next := (timestamp := data.get(timestamp_key, 0)) + (60 * 60 * 12)):
        reminder_key = f'daily_reminder:{ctx.user_id}'
        if reminder_key in data:
          del data[reminder_key]
        data[timestamp_key] = now
        reward = random.randint(10, 100 if subbed else 50)
        bal_key = f'bal:{ctx.user_id}'
        bal = data[bal_key] = data.get(bal_key, 0) + reward
        if timestamp == 0:
          data['bal:sorted'] = list(sorted(data['bal:sorted'] + [str(ctx.user_id)], key=lambda u: data.get(f'bal:{u}', 0), reverse=True))
        await data.save('daily claimed')
        emoji = data['currency_emoji']
        await ctx.reply(f'Thanks for claiming your daily! Got {reward}{emoji} {" (sub bonus)" if subbed else ""}, Total: {bal}{emoji}')
      else:
        minutes_remaining = (time_next - now) // 60
        hours, minutes = map(int, divmod(minutes_remaining, 60))
        await ctx.reply(f'You have already claimed a daily recently. Try again in {hours} hour{"s" if hours != 1 else ""} and {minutes} minute{"s" if minutes != 1 else ""}.')
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
      await data.save('box purchased')
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
  #   data.save('box opened')

  #   items_str = '\n' + '\n'.join(f'{item["rarity"]} {item["name"]} [+{item["rarity_stat"]} {item["stat_type"]}]' for item in items) + '\n\n'

  #   await ctx.reply(f'Obtained: {items_str}')

  async def sub_command(ctx: Context, *args):
    if await ctx.check_sub():
      await ctx.reply('uwu yes you are a sub')
    elif ctx.source_type is discord.Context:
      await ctx.reply('wtf why aren\'t you subbed???? (if you\'re actually subbed, make sure your Twitch account is linked to your Discord account in the Connections page)')
    elif ctx.source_type is PetalContext:
      await ctx.reply('wtf why aren\'t you subbed???? (if you\'re actually subbed, this is an indication that you are not currently cached by Twitch as a chatter)')
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
    remind_command,
    unremind_command,
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

  async def daily_reminders_task():
    await discord_bot.wait_until_ready()

    while discord_bot.is_ready():
      for discord_id in data['daily_reminders_list']:
        twitch_id = data[f'discord:{discord_id}']
        reminder_key = f'daily_reminder:{twitch_id}'
        if data.get(reminder_key) is not None:
          continue

        if time.time() >= data.get(f'daily_ts:{twitch_id}', 0) + (60 * 60 * 12):
          await (await discord_bot.fetch_user(discord_id)).send('You can use the daily command again!')
          data[reminder_key] = True
          await data.save('stored reminder flag')
      await asyncio.sleep(60)

  async def subathon_task():
    await discord_bot.wait_until_ready()

    alerts_channel = discord_bot.get_channel(constants.DISCORD_ALERTS_CHANNEL_ID)
    sent_timer_alert = False

    while discord_bot.is_ready():
      async with aiopen(constants.SUBATHON_TIMER_FILE) as aiof:
        clock_text = await aiof.read()
      if clock_text:
        hours, minutes, __seconds = map(int, clock_text.split(':'))
        print(f'[TIMER CHECK] {hours}:{minutes}:{__seconds}')
        if hours * 60 + minutes < constants.SUBATHON_TIMER_ALERT_THRESHOLD:
          if not sent_timer_alert:
            discord_bot.log_info('sending subathon alert')
            await alerts_channel.send(constants.SUBATHON_TIMER_ALERT_FORMAT.format(
              constants.DISCORD_TIMER_ALERTS_ROLE_ID,
              constants.BROADCASTER_CHANNEL
            ))
            sent_timer_alert = True
            discord_bot.log_info('subathon alert sent')
        else:
          sent_timer_alert = False
        await asyncio.sleep(constants.SUBATHON_TIMER_ALERT_TIMEOUT)

  async def live_indicator_task():
    # TODO: add logging
    await discord_bot.wait_until_ready()

    live_voice_channel = discord_bot.get_channel(constants.DISCORD_LIVE_VOICE_CHANNEL_ID)
    live_indicator_active = False

    while discord_bot.is_ready():
      if await is_live():
        if not live_indicator_active:
          await twitter_bot.api.account.update_profile.post(
            name=constants.TWITTER_LIVE_DISPLAY_NAME
          )
          await live_voice_channel.guild.edit(name=constants.DISCORD_LIVE_GUILD_NAME)
          live_indicator_active = True
      elif live_indicator_active:
        await twitter_bot.api.account.update_profile.post(
          name=constants.TWITTER_DISPLAY_NAME
        )
        await live_voice_channel.guild.edit(name=constants.DISCORD_GUILD_NAME)
        live_indicator_active = False
      await asyncio.sleep(constants.LIVE_INDICATOR_TIMEOUT)

  await discord_bot.login(constants.DISCORD_TOKEN)
  asyncio.create_task(daily_reminders_task())
  asyncio.create_task(subathon_task())
  asyncio.create_task(live_indicator_task())
  asyncio.create_task(petal_bot.login())
  await asyncio.gather(*(bot.connect() for bot in [twitch_bot, discord_bot]))

if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    exit()
