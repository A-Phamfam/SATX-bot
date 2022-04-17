from main import SATXBot
import datetime
from datetime import datetime
import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands, tasks
import parsedatetime
import pytz


class TestCog(commands.Cog):
    def __init__(self, bot: SATXBot):
        self.bot: SATXBot = bot
        self.events = []

    @commands.slash_command(description="Test command.")
    async def test(self, inter: AppCmdInter):
        rsvp_embed = (disnake.Embed(title="RSVP List")
                      .add_field(name="Going", value="* *")
                      .add_field(name="Maybe", value="* *")
                      .add_field(name="Not Going", value="* *"))
        q = rsvp_embed.to_dict()
        print(rsvp_embed.to_dict)
        await inter.response.send_message(embed=rsvp_embed)

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

    city_locations = {x: x for x in ["DTX", "HTX", "ATX", "SATX"]}

    @commands.slash_command()
    async def test_user_location(self, inter: AppCmdInter,
                                 event_location: commands.option_enum(city_locations)):
        await inter.response.send_message(f"You chose {event_location}")

    # EVENT LISTENERS
    @commands.Cog.listener(name="on_member_join")
    async def on_member_join(self, member: disnake.Member):
        test_channel = self.bot.get_channel(961770441532395550)
        await test_channel.send(f"Hi <@{member.id}>!")

    @commands.Cog.listener("on_guild_scheduled_event_subscribe")
    async def send_hi(self, event: disnake.GuildScheduledEvent, user: disnake.Member):
        test_channel = self.bot.get_channel(self.bot.keys.EVENT_CHANNEL_ID)
        await test_channel.send(f"<@{user.id}> is interested in {event.name}!")

    @commands.Cog.listener("on_guild_scheduled_event_subscribe")
    async def ask_rsvp(self, event: disnake.GuildScheduledEvent, user: disnake.Member):
        if event.creator.id == user.id:
            return
        await user.send(f"You are intersted in {event.name}! If you are interested in going please RSVP.")
        await event.creator.send(f"<@{user.id}> is interested in attending your event {event.name}!")

    @commands.Cog.listener("on_message_edit")
    async def reply_hi(self, message_before: disnake.Message, message_after: disnake.Message):
        await message_after.reply("hi")

    # EVENT LOOPS
    @tasks.loop(minutes=5)
    async def rsvp_reminder(self):
        bot_guild = await self.bot.fetch_guild(self.bot.keys.TEST_SERVER_ID)
        guild_events = await bot_guild.fetch_scheduled_events()
        for event in guild_events:
            if event.scheduled_start_time - datetime.today() < datetime.timedelta(0):
                event_members = await event.fetch_users()
                for member in event_members:
                    await member.send("Remember to RSVP!")


def setup(bot: SATXBot):
    bot.add_cog(TestCog(bot))
