import datetime

import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands, tasks
import parsedatetime
import pytz


class TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guilds = []
        self.events = []

    @commands.Cog.listener(name="on_member_join")
    async def on_member_join(self, member):
        print('test')

    @commands.slash_command(description="Test thread")
    async def test_thread(self, inter: AppCmdInter, thread_name: str):
        thread_message = await inter.channel.send(thread_name)
        await thread_message.create_thread(
            name=thread_name,
        )
        await inter.response.send_message(f"Thread created <@{inter.user.id}>", ephemeral=True)

    @commands.slash_command(description="datetime parse")
    async def test_parse_datetime(self, inter: AppCmdInter, datetime_string: str):
        cal = parsedatetime.Calendar()
        datetime_obj, _ = cal.parseDT(datetimeString=datetime_string, tzinfo=pytz.timezone('US/Central'))
        await inter.response.send_message(f"{datetime_obj}")

    @commands.slash_command()
    async def test_event_parse(self, inter: AppCmdInter, datetime_string: str):
        cal = parsedatetime.Calendar()
        datetime_obj, _ = cal.parseDT(datetimeString=datetime_string, tzinfo=pytz.timezone('US/Central'))
        event = await inter.guild.create_scheduled_event(
            name="test",
            description="testdesc",
            entity_type=disnake.GuildScheduledEventEntityType.external,
            entity_metadata=disnake.GuildScheduledEventMetadata(location="testloc"),
            scheduled_start_time=datetime_obj,
            scheduled_end_time=datetime_obj + datetime.timedelta(hours=2))
        await inter.response.send(f"<@{inter.author.id}> created the event {event.id}")

    @commands.slash_command(description="test create event")
    async def test_create_event(self, inter: AppCmdInter, event_name: str, event_location: str, event_time: str):
        await inter.guild.create_scheduled_event()

    @commands.Cog.listener("on_message_edit")
    async def reply_hi(self, message_before: disnake.Message, message_after: disnake.Message):
        await message_after.reply("hi")

    @commands.Cog.listener("on_guild_scheduled_event_create")
    async def reply_hi(self, event: disnake.GuildScheduledEvent):
        print("event created")
        test_channel = self.bot.get_channel(961770441532395550)
        await test_channel.send(
            f"Event Name: {event.name}\n Event Description: {event.description}\n Owner: <@{event.creator_id}")

    @commands.slash_command(description="Test command.")
    async def test(self, inter: AppCmdInter):
        await inter.response.send_message("test")
        await inter.channel.send("test2")
        await inter.channel.send("test3")


def setup(bot: commands.Bot):
    bot.add_cog(TestCog(bot))
