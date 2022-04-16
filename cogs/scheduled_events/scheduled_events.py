import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands, tasks
import re
import yaml
from main import SATXBot
from typing import Dict, List


class EventRecords:
    def __init__(self, event_to_thread: Dict[int, int], event_rsvped: Dict[int, List[int]]):
        self.event_to_thread = event_to_thread
        self.event_rsvped = event_rsvped

    async def rewrite_to_yaml(self):
        async with open("event_records.yaml", "w") as records:
            yaml.dump(self.__dict__, records)


class ScheduledEventCog(commands.Cog):
    def __init__(self, bot: SATXBot):
        self.bot = bot
        self.event_records: EventRecords = None
        self.irl_events_channel: disnake.TextChannel = None
        self.metroplex_roles = {}

    async def create_thread(self, event: disnake.GuildScheduledEvent):
        event_link = await get_event_link(event.guild_id, event.id)
        event_metroplex = await get_metroplex_listed(event.name)

        if not event_metroplex:
            # Notify bot owner to fix the event so that the proper role can be pinged.
            bot_owner = self.bot.get_user(self.bot.keys.BOT_OWNER_ID)
            await bot_owner.send(f"The following event does not list the metroplex. "
                                 f"Please edit and fix the event for the thread to be created. \n"
                                 f"{event_link}")
            return

        # Announce event and create thread
        metro_role_id = self.metroplex_roles[event_metroplex]
        announce_msg = await self.irl_events_channel.send(f"<@{metro_role_id}>\n" + "New Event!!\n" + event_link)
        event_thread = await announce_msg.create_thread(name=event.name)

        # Add the event thread to the event records
        self.event_records.event_to_thread[event.id] = event_thread.id
        await self.event_records.rewrite_to_yaml()

    @commands.Cog.listener(name="on_guild_scheduled_event_create")
    async def thread_creation(self, event: disnake.GuildScheduledEvent):
        await self.create_thread(event)

    @commands.Cog.listener(name="on_guild_scheduled_event_update")
    async def retry_thread_creation(self, event_before, event_after: disnake.GuildScheduledEvent):
        if event_after.id not in self.event_records.event_to_thread:
            await self.create_thread(event_after)

    @commands.Cog.listener(name="on_guild_scheduled_event_subscribe")
    async def ping_person_in_thread(self, event: disnake.GuildScheduledEvent, subscriber: disnake.Member):
        event_thread = self.bot.get_channel(self.event_records.event_to_thread[event.id])
        await event_thread.send(f"<@{subscriber.id}> is interested in {event.name}!")

    @commands.Cog.listener(name="on_ready")
    async def read_from_event_records(self):
        # Initialize the record of existing events to their threads and RSVPed Users
        with open("event_records.yaml", "r") as f:
            self.event_records = EventRecords(**yaml.safe_load(f))
        print(f"{len(self.event_records.event_to_thread)} events have been read from event_records.yaml")

    @commands.Cog.listener(name="on_ready")
    async def read_event_config(self):
        # Initialize the IRL events channel and metroplex roles from configs
        with open("event_config.yaml", "r") as f:
            config = yaml.safe_load(f)
            self.irl_events_channel = self.bot.get_channel(config["irl_events_channel_id"])
            self.metroplex_roles = config["metroplex_roles"]
        print(f"The IRL events channel ID was read as {config['irl_events_channel_id']} from event_config.yaml")
        print(f"The metroplex roles from event_config.yaml were {config['metroplex_roles']}")


async def get_event_link(guild_id: int, event_id: int) -> str:
    return f"https://discord.com/events/{guild_id}/{event_id}"


async def get_metroplex_listed(input_string: str):
    metroplex_regex = r"\[((?:DTX)|(?:SATX)|(?:ATX)|(?:HTX))|(?:CSTAT)\]"
    return re.match(metroplex_regex, input_string)[0]


def setup(bot: SATXBot):
    bot.add_cog(ScheduledEventCog(bot))
