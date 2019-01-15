import asyncio
import discord
import time
from related import Related
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path  # python3 only
import os

if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')


class VoiceEntry:
    def __init__(self, player, channel, author=None):
        self.requester = author
        self.channel = channel
        self.player = player

    def __str__(self):
        fmt = '*[{0.title}]({2})*'
        if 'http' in self.player.url:
            url = self.player.url
        else:
            url = ''
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester, url)


class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.channel = None
        self.voice = None
        self.bot = bot
        self.auto_play = True
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.songs_history = []
        self.entries_history = []
        self.skip_votes = set()  # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.create_task(self.play_next())

    async def play(self, song, message=None, channel=None):
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }
        try:
            player = await self.voice.create_ytdl_player(song, ytdl_options=opts, after=self.toggle_next)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            if channel:
                await self.bot.send_message(channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.5
            requester = message.author if message else None
            if channel is None:
                channel = self.channel
            else:
                self.channel = channel
            entry = VoiceEntry(player, channel, requester)
            if message:
                embed = discord.Embed(
                    colou=discord.Color.blue()
                )
                embed.add_field(name='Enqueued', value=str(entry))
                await self.bot.say(embed=embed)
            await self.songs.put(entry)
            self.entries_history.append(entry)

    async def play_next(self):
        if self.songs.empty() and self.auto_play:
            player = self.current.player
            try:
                yt_id = player.yt.extract_info(player.url, download=False)["entries"][0]["id"]
            except:
                yt_id = player.yt.extract_info(player.url, download=False)["id"]
            self.songs_history.append(yt_id)
            related_song = Related(YT_KEY).url_to_first_related(yt_id, self.songs_history)
            if related_song is None:
                print('Can\'t find related songs')
            else:
                await self.play(related_song)
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            print('task {}'.format(time.ctime()))
            self.play_next_song.clear()
            self.current = await self.songs.get()
            if self.current.channel:
                embed = discord.Embed(
                    colour=discord.Color.blue()
                )
                field = str(self.current)
                embed.add_field(name='Now playing', value=field)
                await self.bot.send_message(self.current.channel, embed=embed)
                # await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()


class Music:
    """Voice related commands.

    Works in multiple servers at once.
    """

    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        self.queue_page_size = 10

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel: discord.Channel):
        """Joins a voice channel."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.bot.say('Already in a voice channel...')
        except discord.InvalidArgument:
            await self.bot.say('This is not a voice channel...')
        else:
            await self.bot.say('Ready to play audio in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song: str):
        """Plays a song.

        If there is a song currently in the queue, then it is
        queued until the next song is done playing.

        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """
        state = self.get_voice_state(ctx.message.server)

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        await state.play(song, ctx.message, ctx.message.channel)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value: int):
        """Sets the volume of the currently playing song."""

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            embed = discord.Embed(
                colour=discord.Color.blue()
            )
            embed.set_author(name="It's me", url="https://vk.com/kaless1n")
            field = 'Set the volume to {:.0%}'.format(player.volume)
            embed.add_field(name='Queue', value=field)
            await self.bot.say(embed=embed)

    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        """Pauses the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.pause()

    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        """Resumes the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.

        This also clears the queue.
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Vote to skip a song. The song requester can automatically skip.

        3 skip votes are needed for the song to be skipped.
        """
        state = self.get_voice_state(ctx.message.server)
        embed = discord.Embed(
            colour=discord.Color.blue()
        )
        embed.set_author(name="It's me", url="https://vk.com/kaless1n")
        if not state.is_playing():
            field = 'Not playing any music right now...'
            embed.add_field(name='Queue', value=field)
            await self.bot.say(embed=embed)
            return

        field = 'Skipping song...'
        embed.add_field(name='Queue', value=field)
        await self.bot.say(embed=embed)
        state.skip()

    @commands.command(pass_context=True, no_pm=True)
    async def auto(self, ctx):
        state = self.get_voice_state(ctx.message.server)
        state.auto_play = not state.auto_play
        if state.auto_play:
            await self.bot.say('Auto play is enabled')
        else:
            await self.bot.say('Auto play is disabled')

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            field = 'Not playing anything.'
        else:
            field = str(state.current)

        embed = discord.Embed(
            colour=discord.Color.blue()
        )
        # embed.set_author(name="It's me", url="https://vk.com/kaless1n")
        embed.add_field(name='Now playing', value=field)
        await self.bot.say(embed=embed)

    def queue_content(self, state, page_number):
        print('page_number')
        print(page_number)
        if state.entries_history is []:
            field = 'Queue is empty'
        else:
            field = ''
            starts_with = page_number * self.queue_page_size
            ends_with = page_number * self.queue_page_size + self.queue_page_size
            for i in range(starts_with, ends_with):
                try:
                    entry = state.entries_history[i]
                    field += str(i + 1) + '. ' + str(entry) + "\n"
                except IndexError:
                    pass

        embed = discord.Embed(
            colour=discord.Color.blue()
        )
        # embed.set_author(name="It's me", url="https://vk.com/kaless1n")
        if not field:
            return None
        embed.add_field(name='Queue', value=field)
        return embed

    @commands.command(pass_context=True, no_pm=True)
    async def queue(self, ctx, ):
        state = self.get_voice_state(ctx.message.server)

        first_time = True
        page_number = 0
        while True:
            if first_time:
                embed = self.queue_content(state, page_number)
                msg = await self.bot.say(embed=embed)
                first_time = False

            toReact = ['⏪', '⏩']

            if len(state.entries_history) > self.queue_page_size:
                for reaction in toReact:
                    await bot.add_reaction(msg, reaction)

            def check_reaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(('⏪', '⏩'))

            res = await bot.wait_for_reaction(message=msg, user=ctx.message.author, timeout=30, check=check_reaction)
            if res is None:
                print('no reaction')
                # for reaction in toReact:
                # await bot.remove_reaction(msg, reaction)
                # await bot.delete_message(ctx.message)
                # await bot.delete_message(msg)
                break
            elif '⏪' in str(res.reaction.emoji):
                print('back reaction')
                page_number = page_number - 1
                if page_number < 0:
                    page_number = 0
                elif page_number > len(state.entries_history):
                    page_number = len(state.entries_history)
                embed = self.queue_content(state, page_number)
                if embed:
                    await bot.edit_message(msg, embed=embed)
            elif '⏩' in str(res.reaction.emoji):
                print('forward reaction')
                page_number = page_number + 1
                if page_number < 0:
                    page_number = 0
                elif page_number > len(state.entries_history):
                    page_number = len(state.entries_history)
                embed = self.queue_content(state, page_number)
                if embed:
                    await bot.edit_message(msg, embed=embed)


bot = commands.Bot(command_prefix=commands.when_mentioned_or('='), description='A playlist example for discord.py')
bot.add_cog(Music(bot))


@bot.event
async def on_ready():
    print('Logged in as:\n{0} (ID: {0.id})'.format(bot.user))


env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)
TOKEN = os.getenv("token")
YT_KEY = os.getenv("yt_key")
bot.run(TOKEN)
