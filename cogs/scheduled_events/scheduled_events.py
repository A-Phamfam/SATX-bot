import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands, tasks
import re
import yaml
from main import SATXBot
from typing import Dict, List
from .rsvp_view import RsvpView


class EventRecords:
    def __init__(self, event_to_thread: Dict[int, int], event_to_message: Dict[int, int],
                 event_to_role: Dict[int, int]):
        self.event_to_thread = event_to_thread
        self.event_to_message = event_to_message
        self.event_to_role = event_to_role

    async def rewrite_to_yaml(self):
        with open("./cogs/scheduled_events/event_records.yaml", "w") as records:
            yaml.dump({"event_to_thread": self.event_to_thread, "event_to_message": self.event_to_message},
                      records)

    async def add_event(self, event_id: int, event_thread_id: int, event_message_id: int, event_role_id: int):
        self.event_to_thread[event_id] = event_thread_id
        self.event_to_message[event_id] = event_message_id
        self.event_to_role[event_id] = event_role_id
        await self.rewrite_to_yaml()

    async def remove_event(self, event_id):
        self.event_to_thread.pop(event_id)
        self.event_to_message.pop(event_id)
        self.event_to_role.pop(event_id)
        await self.rewrite_to_yaml()


class ScheduledEventCog(commands.Cog):
    def __init__(self, bot: SATXBot):
        self.bot = bot
        self.event_records: EventRecords = None
        self.irl_events_channel: disnake.TextChannel = None
        self.metroplex_roles = {}
        self.rsvp_messages = {}

    """ Thread Creation """

    async def create_thread(self, event: disnake.GuildScheduledEvent):
        event_link = await get_event_link(event.guild_id, event.id)
        event_metroplex = await get_metroplex_listed(event.name)

        if not event_metroplex:
            await self.alert_invalid_event_name(event_link)
            return

        # Announce event and create thread
        metro_role_id = self.metroplex_roles[event_metroplex]
        announce_msg = await self.irl_events_channel.send(f"<@&{metro_role_id}>\n" + "New Event!!\n" + event_link)
        event_thread = await announce_msg.create_thread(name=event.name)
        await self.initialize_bot_event_management(announce_msg, event, event_thread, metro_role_id)

    async def initialize_bot_event_management(self,
                                              announce_msg: disnake.Message,
                                              event: disnake.GuildScheduledEvent,
                                              event_thread: disnake.Thread,
                                              metro_role_id: int):
        event_role = await create_event_role(event.name, event.guild, metro_role_id)
        await event_thread.send(f"<@{event.creator_id}> is the host of this event!\n\n"
                                f"The pingable role <@&{event_role.id}> has been created for you "
                                f"to ping all interested members.\n"
                                f"When you are ready, use the `/send_rsvp` command for an RSVP message to be DMed "
                                f"to all interested users. The updated RSVP list will be sent to you.")
        await self.event_records.add_event(event.id, event_thread.id, announce_msg.id, event_role.id)

    async def alert_invalid_event_name(self, event_link):
        # Notify bot owner to fix the event so that the proper role can be pinged.
        bot_owner = self.bot.get_user(self.bot.keys.BOT_OWNER_ID)
        await bot_owner.send(f"The following event does not list the metroplex. "
                             f"Please edit and fix the event for the thread to be created. \n"
                             f"{event_link}")

    @commands.Cog.listener(name="on_guild_scheduled_event_create")
    async def thread_creation(self, event: disnake.GuildScheduledEvent):
        await self.create_thread(event)

    @commands.Cog.listener(name="on_guild_scheduled_event_update")
    async def retry_thread_creation(self, event_before, event_after: disnake.GuildScheduledEvent):
        if (not self.event_records.event_to_thread) or (event_after.id not in self.event_records.event_to_thread):
            await self.create_thread(event_after)

    """ Event Role """
    @commands.Cog.listener(name="on_guild_scheduled_event_update")
    async def rename_event_role_name(self, event_before: disnake.GuildScheduledEvent,
                                     event_after: disnake.GuildScheduledEvent):
        if event_before.name == event_after.name:
            return
        event_guild = await self.bot.fetch_guild(event_after.guild_id)
        event_role_id = self.event_records.event_to_role[event_after.id]
        event_role = event_guild.get_role(event_role_id)
        await event_role.edit(name=event_after.name)

    @commands.Cog.listener(name="on_guild_scheduled_event_delete")
    async def remove_event_role(self, event):
        event_guild = await self.bot.fetch_guild(event.guild_id)
        event_role_id = self.event_records.event_to_role[event.id]
        event_role = event_guild.get_role(event_role_id)
        await event_role.delete()

        await self.event_records.remove_event(event.id)

    @commands.Cog.listener(name="on_guild_scheduled_event_subscribe")
    async def ping_person_in_thread(self, event: disnake.GuildScheduledEvent, subscriber: disnake.Member):
        if subscriber.id == event.creator_id:
            return
        event_thread = self.bot.get_channel(self.event_records.event_to_thread[event.id])
        await event_thread.send(f"<@{subscriber.id}> is interested in {event.name}!")

    """ RSVP Message """

    async def send_rsvp_message(self, event: disnake.GuildScheduledEvent,
                                subscriber: disnake.Member) -> disnake.Message:
        event_thread = self.bot.get_channel(self.event_records.event_to_thread[event.id])
        event_creator = await self.bot.fetch_user(event.creator_id)

        rsvp_embed = await get_empty_rsvp_embed(event.creator_id)
        event_message = await event_creator.send(embed=rsvp_embed)

        rsvp_view = RsvpView(event, event_thread, event_message, subscriber, event_creator)
        return await subscriber.send(embed=rsvp_view.dm_embed, view=rsvp_view)

    @commands.slash_command(description="Send slash commands for this event to all interested users.")
    async def send_rsvp(self, inter: AppCmdInter):
        event_id_of_thread = get_key(self.event_records.event_to_thread, inter.channel_id)
        if not event_id_of_thread:
            inter.response.send("This command can only be used in a valid event thread.", ephemeral=True)
        event = await inter.guild.fetch_scheduled_event(event_id_of_thread)
        if inter.author.id != event.creator_id:
            inter.response.send("This command can only be used by the event creator.", ephemeral=True)
        event_subscribers = await event.fetch_users()
        for subscriber in event_subscribers:
            if subscriber.id == event.creator_id:
                continue
            rsvp_msg = await self.send_rsvp_message(event, subscriber)
            self.rsvp_messages[event.id].append(rsvp_msg.id)

    @commands.Cog.listener(name="on_guild_scheduled_event_delete")
    async def delete_all_rsvp_messages(self, event):
        for rsvp_msg_id in self.rsvp_messages[event.id]:
            msg = self.bot.get_message(rsvp_msg_id)
            await msg.delete()
        self.rsvp_messages.pop(event.id)

    """ Bot Initialization """
    @commands.Cog.listener(name="on_ready")
    async def read_from_event_records(self):
        # Initialize the record of existing events to their threads and RSVPed Users
        with open("./cogs/scheduled_events/event_records.yaml", "r") as f:
            self.event_records = EventRecords(**yaml.safe_load(f))
        if self.event_records.event_to_thread:
            print(f"{len(self.event_records.event_to_thread)} events have been read from event_records.yaml")

    @commands.Cog.listener(name="on_ready")
    async def read_event_config(self):
        # Initialize the IRL events channel and metroplex roles from configs
        with open("./cogs/scheduled_events/event_config.yaml", "r") as f:
            config = yaml.safe_load(f)
            self.irl_events_channel = self.bot.get_channel(config["irl_events_channel_id"])
            self.metroplex_roles = config["metroplex_roles"]
        print(f"The IRL events channel ID was read as {config['irl_events_channel_id']} from event_config.yaml")
        print(f"The metroplex roles from event_config.yaml were {config['metroplex_roles']}")

    @commands.message_command(name="Start Event Management")
    async def start_event_management(self, inter: AppCmdInter, event_msg: disnake.Message):
        if inter.author.id != self.bot.keys.BOT_OWNER_ID:
            inter.response.send("Only the bot owner can use this command.", ephemeral=True)
        event_id = await find_event_id(event_msg.content)
        event = await inter.guild.fetch_scheduled_event(event_id)
        if not event:
            inter.response.send("No valid event link was found in this message.", ephemeral=True)
            return

        event_thread = event_msg.thread
        if not event_thread:
            inter.response.send("There is not a valid event thread connected to this message.", ephemeral=True)
            return

        metro_role_id = await find_metro_role_id(event_msg.content)
        if not metro_role_id:
            inter.response.send("No metro events role was found in this message.", ephemeral=True)
            return

        await self.initialize_bot_event_management(event_msg, event, event_thread, metro_role_id)


async def get_event_link(guild_id: int, event_id: int) -> str:
    return f"https://discord.com/events/{guild_id}/{event_id}"


async def find_event_id(input_string: str) -> int:
    event_id_regex = r"https:\/\/discord\.com\/events\/\d{18}\/(\d{18})"
    event_id_match = re.match(event_id_regex, input_string)
    if event_id_match:
        return int(event_id_match[1])


async def find_metro_role_id(input_string: str) -> int:
    metro_id_regex = r"<@&(\d{18})>"
    metro_id_match = re.match(metro_id_regex, input_string)
    if metro_id_match:
        return int(metro_id_match[1])


async def create_event_role(event_name: str, guild: disnake.Guild, metro_role_id: int) -> disnake.Role:
    metro_role = guild.get_role(metro_role_id)
    return await guild.create_role(name=event_name, color=metro_role.color, mentionable=True)


async def get_empty_rsvp_embed(event_creator_id):
    rsvp_embed = (disnake.Embed(title="RSVP List")
                  .add_field(name="Going", value=f"<@{event_creator_id}")
                  .add_field(name="Maybe", value="* *")
                  .add_field(name="Not Going", value="* *"))
    return rsvp_embed


async def get_metroplex_listed(input_string: str):
    metroplex_regex = r"\[((?:DTX)|(?:SATX)|(?:ATX)|(?:HTX)|(?:CSTAT))\]"
    metro_match = re.match(metroplex_regex, input_string)
    if metro_match:
        return metro_match[1]


def get_key(my_dict, val):
    for key, value in my_dict.items():
        if val == value:
            return key


def setup(bot: SATXBot):
    bot.add_cog(ScheduledEventCog(bot))
