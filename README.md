# lynnya_bot
Twitch / Discord / Twitter bot for https://twitch.tv/lynnya_tw

## Quick start
1. Copy `.env.example` to a new text file named `.env` (notice there is no .txt extension, this is intentional)
2. Review all of the settings in this new file. These will need to be updated by you in order for the bot to function.
3. You'll notice that a lot of these settings are tokens for other services or are hard to understand, so please read the sections below if you need help.
4. Run `install.bat` if you're on Windows, or `install.sh` otherwise. If the script fails for some reason, just use `pip` to install the modules in `requirements.txt` if you know how.
5. Finally, run the bot with `py bot.py` if you are on Windows, or `python3 bot.py` otherwise. If you are not using a terminal, you can probably double-click `bot.py` and your operating system should work out how to run the application for you.
6. If you need additional help running the bot, please DM me on Discord (`lynn#3368`) instead of creating a GitHub issue, unless you're actually reporting a bug or requesting a new feature.

### Adding a Discord token
1. Go to the [Discord developer page](https://discord.com/developers/applications) and log in.
2. Create a new application, select the new application, and click "Bot" on the left.
3. Create a bot user, then click the "Copy" button under the reveal token link.
4. Replace `DISCORD_TOKEN` with this value.

### Adding a Twitch token
1. Create a [new Twitch account](https://www.twitch.tv/signup) for the bot user if you haven't already
2. Go to the (unofficial) [Twitch OAuth Generator page](https://twitchapps.com/tmi/) and log in as the bot user.
3. Remove `oauth:` from the start of the token and replace `TWITCH_TOKEN` with this modified value.

### Adding Twitter API credentials
1. Create a Twitter [Developer account](https://developer.twitter.com/en) if you don't already have one.
2. Go to the [Twitter developer page](https://developer.twitter.com/en/portal/dashboard) and log in.
3. Create a new application, and copy the 4 values mentioned in step 5 as you go (generate them if they're not already shown).
4. Optional: Click the cog icon (App Settings), Keys and tokens, and click "Regenerate" for any values that you missed in the previous step.
5. Replace `TWITTER_KEY`, `TWITTER_SECRET`, `TWITTER_ACCESS_TOKEN`, and `TWITTER_ACCESS_TOKEN_SECRET` with these values.
6. In order to send tweets on your behalf, the bot needs [Elevated access](https://developer.twitter.com/en/portal/petition/essential/basic-info) to the Twitter API, which is something you have to apply for. There's really no reason they will reject your application as long as you write some sensible summary of what the bot will do (likely just sending tweets to notify your followers when you are streaming).

### Adding the other settings
1. `BOT_NAME` is just the name of your bot application. It displays in the terminal when you start the bot.
2. `BROADCASTER_CHANNEL` is your username on Twitch, **not the full URL**. It's used to form your channel URL and provides additional Twitch-related functionality.
3. `DISCORD_STAFF_CHANNEL_ID` is an ID of a channel that only your trusted Discord staff have access to. It's used to allow trusted staff members to use administrative commands from Discord. Please note that this is **NOT** a role ID, and can be either a category ID, text channel ID, or voice channel ID, it doesn't matter.
4. `DISCORD_CHANNEL_IDS` is a list of IDs for channels users should use the commands in. You can provide multiple channels by separating the IDs with commas.
5. `DISCORD_LIVE_VOICE_CHANNEL_ID` is the ID of the voice channel that you want to join while streaming. It will automatically "close" and hide itself when you disconnect.
6. `DISCORD_CLOSED_VOICE_CHANNEL_ID` is the ID of the voice channel that you only want to move members to automatically when you leave the "live" voice channel.
7. `DISCORD_ALERTS_ROLE_ID` is the ID of the role that you want to @mention when you are live. This is for the `alert` administrative command, which mentions the role with a description of your current livestream and also tweets a stream summary for you.
8. `DATA_PATH` is the location that runtime data will save to. By default, this value is `data.json`, relative to the directory `bot.py` is executed from.
9. `DEFAULT_PREFIX` is the default prefix used for all services when they're not already set.
10. `DEFAULT_CURRENCY_EMOJI` is the default currency emoji used when it's not already set.
11. The remainder of the settings are related to logging, and you shouldn't need to change them unless you want to customize your terminal output.

#### Developers: To-do list
1. Add a guide here for all the included commands
2. Migrate the data layer to Redis
3. Add the ability to change broadcaster data with a broadcaster Twitch token (specifics for this are TBD)
