import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands
import re
import yaml
from main import SATXBot
from typing import Dict, List
from .rsvp_view import RsvpView
from util import logger


class EventRecords:
    """
    Dataclass to hold the thread, message, and role for each event and handles updating the YAML file.
    """

    def __init__(self, event_to_thread: Dict[int, int], event_to_message: Dict[int, int],
                 event_to_role: Dict[int, int]):
        self.event_to_thread = event_to_thread
        self.event_to_message = event_to_message
        self.event_to_role = event_to_role

    async def rewrite_to_yaml(self):
        with open("./cogs/scheduled_events/event_records.yaml", "w") as records:
            yaml.dump({"event_to_thread": self.event_to_thread,
                       "event_to_message": self.event_to_message,
                       "event_to_role": self.event_to_role},
                      records)

    async def add_event(self, event_id: int, event_thread_id: int, event_message_id: int, event_role_id: int):
        self.event_to_thread[event_id] = event_thread_id
        self.event_to_message[event_id] = event_message_id
        self.event_to_role[event_id] = event_role_id
        logger.info(f"Event records has recorded {event_id}: [{event_thread_id}, {event_message_id}, {event_role_id}]")
        await self.rewrite_to_yaml()

    async def remove_event(self, event_id):
        self.event_to_thread.pop(event_id)
        self.event_to_message.pop(event_id)
        self.event_to_role.pop(event_id)
        logger.info(f"Event records has removed {event_id}.")
        await self.rewrite_to_yaml()


class ScheduledEventCog(commands.Cog):
    def __init__(self, bot: SATXBot):
        self.bot = bot
        self.event_records: EventRecords = None
        self.irl_events_channel: disnake.TextChannel = None
        self.metroplex_roles = {}
        self.rsvp_messages = {}
        self.rsvp_list_messages = {}

    @commands.Cog.listener()
    async def on_ready(self):
        await self.read_from_event_records()
        await self.read_event_config()

        guild = await self.bot.fetch_guild(self.bot.keys.TEST_SERVER_ID)
        events = await guild.fetch_scheduled_events()
        roles = await guild.fetch_roles()

        await self.add_all_late_roles(guild, events)
        await self.remind_of_events(events)
        await self.purge_old_events(guild)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_create(self, event: disnake.GuildScheduledEvent):
        await self.announce_event_and_create_thread(event)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_update(self, event_before: disnake.GuildScheduledEvent,
                                              event_after: disnake.GuildScheduledEvent):
        await self.retry_thread_creation(event_before, event_after)
        await self.rename_event_role_and_thread(event_before, event_after)
        if event_after.status == disnake.GuildScheduledEventStatus.completed\
                and self.event_records.event_to_thread.get(event_after.id):
            await self.delete_event(event_after.guild_id, event_after.id)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_subscribe(self, event: disnake.GuildScheduledEvent, subscriber: disnake.Member):
        await self.add_role_and_ping_in_thread(event, subscriber)
        await self.send_late_rsvp(event, subscriber)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_unsubscribe(self, event: disnake.GuildScheduledEvent,
                                                   subscriber: disnake.Member):
        await self.unsubscribe_event_role(event, subscriber)

    @commands.Cog.listener()
    async def on_guild_scheduled_event_delete(self, event: disnake.GuildScheduledEvent):
        await self.delete_event(event.guild_id, event.id)

    """ Announcement and Thread Creation """

    @commands.message_command(name="Start Event Management")
    async def event_management(self, inter: AppCmdInter, event_msg: disnake.Message):
        await inter.response.defer(ephemeral=True)
        if inter.author.id not in [self.bot.keys.BOT_OWNER_ID, self.bot.keys.TEST_SERVER_MOD_ID]:
            await inter.followup.send("Only the bot owner can use this command.", ephemeral=True)
            return

        event_id = await find_event_id(event_msg.content)
        if not event_id:
            await inter.followup.send("No valid event link was found in this message.", ephemeral=True)
            return
        event = await inter.guild.fetch_scheduled_event(event_id)

        event_thread_id = event_msg.thread.id
        event_thread = await inter.guild.fetch_channel(event_thread_id)
        if not event_thread:
            await inter.followup.send("There is not a valid event thread connected to this message.",
                                      ephemeral=True)
            return

        metro_role_id = await find_metro_role_id(event_msg.content)
        if not metro_role_id:
            await inter.followup.send("No metro events role was found in this message.", ephemeral=True)
            return

        if self.event_records.event_to_thread.get(event_id):
            await inter.followup.send("This event already is being managed by the bot.", ephemeral=True)
            return

        event_role = await create_event_role(event.name, event_msg.guild, metro_role_id)
        event_role = await add_event_role_to_users(event_role, event, metro_role_id)
        await self.send_help_message(event_msg, event, event_thread, event_role)
        await inter.followup.send("Event management successful.", ephemeral=True)

    async def get_event_message(self, event: disnake.GuildScheduledEvent):
        """
        Get the event announcement message.
        """
        event_link = await get_event_link(event.guild_id, event.id)
        event_metroplex = await get_metroplex_listed(event.name)
        metro_role_id = self.metroplex_roles.get(event_metroplex)
        return f"<@&{metro_role_id}>\n" + f"New event: {event.name}\n" + event_link

    async def announce_event_and_create_thread(self, event: disnake.GuildScheduledEvent):
        """
        Creates the announcement message and creates the corresponding thread.
        """
        event_link = await get_event_link(event.guild_id, event.id)
        event_metroplex = await get_metroplex_listed(event.name)

        # Event does not have the correct tag so alert the bot owner
        if not (await get_metroplex_listed(event.name)):
            await self.alert_invalid_event_name(event_link)
            logger.info(f"{event.name} ({event_link}) has no metro and the bot owner has been notified.")
            return

        # Announce event and create thread
        announce_msg = await self.irl_events_channel.send(await self.get_event_message(event))
        event_thread = await announce_msg.create_thread(name=event.name)
        logger.info(f"**{event.name}** has been announced ({announce_msg.jump_url}).")

        # Start event role management
        metro_role_id = self.metroplex_roles.get(event_metroplex)
        event_role = await create_event_role(event.name, event.guild, metro_role_id)
        event_role = await add_event_role_to_users(event_role, event, metro_role_id)
        await self.send_help_message(announce_msg, event, event_thread, event_role)

    async def send_help_message(self,
                                announce_msg: disnake.Message,
                                event: disnake.GuildScheduledEvent,
                                event_thread: disnake.Thread,
                                event_role: disnake.Role
                                ):
        await event_thread.send(f"<@{event.creator_id}> is the host of this event!")
        await event_thread.send(f"You can ping <@&{event_role.id}> to talk to all interested users.")
        await event_thread.send(f"The host can use the `/send_rsvp` command for an RSVP message to be DMed "
                                f"to all interested users. The updated RSVP list will be sent to you.")
        await self.event_records.add_event(event.id, event_thread.id, announce_msg.id, event_role.id)

    async def alert_invalid_event_name(self, event_link):
        """
        Notify bot owner to fix the event so that the proper role can be pinged.
        """
        bot_owner = self.bot.get_user(self.bot.keys.TEST_SERVER_MOD_ID)
        await bot_owner.send(f"The following event does not list the metroplex tag. "
                             f"Please edit and fix the event for the thread to be created. \n"
                             f"{event_link}")

    async def retry_thread_creation(self, event_before, event_after: disnake.GuildScheduledEvent):
        if (not self.event_records.event_to_thread) or (event_after.id not in self.event_records.event_to_thread):
            await self.announce_event_and_create_thread(event_after)

    """ Event Role """

    async def rename_event_role_and_thread(self, event_before: disnake.GuildScheduledEvent,
                                           event_after: disnake.GuildScheduledEvent):
        if event_before.name == event_after.name:
            return
        if event_after.id not in self.event_records.event_to_thread.keys():
            return

        event_role = await self.fetch_event_role(event_after.guild_id, event_after.id)
        event_guild = await self.bot.fetch_guild(event_after.guild_id)
        event_thread = await event_guild.fetch_channel(self.event_records.event_to_thread.get(event_after.id))

        await event_role.edit(name=event_after.name)
        await event_thread.edit(name=event_after.name)

        event_message = await self.irl_events_channel.fetch_message(
            self.event_records.event_to_message.get(event_after.id))

        if event_message.author.id == self.bot.keys.BOT_ID:
            await event_message.edit(content=(await self.get_event_message(event_after)))

        logger.info(f"Event ({event_after.id}) has changed from **{event_before.name}** to {event_after.name}")

    async def add_role_and_ping_in_thread(self, event: disnake.GuildScheduledEvent, subscriber: disnake.Member):
        if subscriber.id == event.creator_id:
            return
        event_thread = self.bot.get_channel(self.event_records.event_to_thread.get(event.id))
        if not event_thread:
            return
        await event_thread.send(f"<@{subscriber.id}> is interested in **{event.name}**!")
        event_role = await self.fetch_event_role(event.guild_id, event.id)
        await subscriber.add_roles(event_role)
        logger.info(f"{subscriber.name} ({subscriber.id}) has added the role {event_role.name} ({event_role.id})")

    async def unsubscribe_event_role(self, event: disnake.GuildScheduledEvent, subscriber: disnake.Member):
        if not self.event_records.event_to_thread.get(event.id):
            return
        event_role = await self.fetch_event_role(event.guild_id, event.id)
        await subscriber.remove_roles(event_role)
        logger.info(f"{subscriber.name} ({subscriber.id}) has removed the role {event_role.name} ({event_role.id})")

    async def fetch_event_role(self, guild_id: int, event_id: int) -> disnake.Role:
        event_role_id = self.event_records.event_to_role.get(event_id)
        guild = await self.bot.fetch_guild(guild_id)
        event_role = guild.get_role(event_role_id)
        if not event_role:
            raise LookupError(f"Fetched event role for {event_role_id}, but it does not exist.")
        return event_role

    """ RSVP Message """

    async def send_rsvp_message(self, event: disnake.GuildScheduledEvent,
                                subscriber: disnake.Member, rsvp_list_message: disnake.Message) -> disnake.Message:
        event_thread = self.bot.get_channel(self.event_records.event_to_thread.get(event.id))
        if not event_thread:
            raise LookupError(f"Event thread {event.id} not found.")
        event_creator = await self.bot.fetch_user(event.creator_id)

        rsvp_view = RsvpView(event, event_thread, rsvp_list_message, subscriber, event_creator)
        rsvp_message = await subscriber.send(embed=rsvp_view.dm_embed, view=rsvp_view)
        logger.info(f"{subscriber.name} ({subscriber.id}) has been sent an RSVP for {event.name} ({event.id})")
        return rsvp_message

    @commands.slash_command(description="Send slash commands for this event to all interested users.")
    async def send_rsvp(self, inter: AppCmdInter):
        await inter.response.defer(ephemeral=True)
        event_id_of_thread = get_key(self.event_records.event_to_thread, inter.channel_id)
        if not event_id_of_thread:
            await inter.followup.send("This command can only be used in a valid event thread.", ephemeral=True)
            return
        event = await inter.guild.fetch_scheduled_event(event_id_of_thread)
        if inter.author.id != event.creator_id:
            await inter.followup.send("This command can only be used by the event creator.", ephemeral=True)
            return
        if self.rsvp_list_messages.get(event.id):
            await inter.followup.send("You have already sent out the RSVP messages.", ephemeral=True)

        # Create and send the RSVP list to the event creator
        event_creator = await self.bot.fetch_user(event.creator_id)
        rsvp_embed = await get_empty_rsvp_embed(event.creator_id, event.name)
        try:
            rsvp_list_message = await event_creator.send(embed=rsvp_embed)
        except:
            await inter.followup.send("I was unable to DM you.", ephemeral=True)
            return
        self.rsvp_list_messages[event.id] = rsvp_list_message.id

        # Create and send the RSVP messages
        self.rsvp_messages[event.id] = []
        event_subscribers = await event.fetch_users()
        for subscriber in event_subscribers:
            if subscriber.id == event.creator_id:
                continue
            try:
                rsvp_msg = await self.send_rsvp_message(event, subscriber, rsvp_list_message)
                self.rsvp_messages[event.id].append(rsvp_msg.id)
            except:
                await event_creator.send(f"<@{subscriber.id}> was not able to be DMed.")

        await inter.followup.send("RSVP messages have been sent!")

    async def send_late_rsvp(self, event: disnake.GuildScheduledEvent, subscriber: disnake.Member):
        if self.rsvp_messages.get(event.id) is None:
            # RSVP messages have not been sent out yet.
            return
        event_thread = await event.guild.fetch_channel(self.event_records.event_to_thread.get(event.id))
        if not event_thread:
            return
        event_creator = await self.bot.fetch_user(event.creator_id)

        rsvp_list_message_id = self.rsvp_list_messages.get(event.id)
        if not rsvp_list_message_id:
            return

        rsvp_list_message = await event_creator.fetch_message(rsvp_list_message_id)

        rsvp_view = RsvpView(event, event_thread, rsvp_list_message, subscriber, event_creator)
        rsvp_msg = await subscriber.send(embed=rsvp_view.dm_embed, view=rsvp_view)
        self.rsvp_messages[event.id].append(rsvp_msg.id)

    async def delete_all_rsvp_messages(self, event_id):
        if self.rsvp_messages.get(event_id) is None:
            # RSVP messages were not sent
            return
        # Delete each individual list
        for rsvp_msg_id in self.rsvp_messages.get(event_id):
            msg = self.bot.get_message(rsvp_msg_id)
            await msg.delete()
        logger.info(f"Deleted {len(self.rsvp_messages.get(event_id))} messages for event {event_id}.")
        self.rsvp_messages.pop(event_id)
        self.rsvp_list_messages.pop(event_id)

    async def delete_event_role(self, guild_id, event_id):
        event_guild = await self.bot.fetch_guild(guild_id)
        event_role_id = self.event_records.event_to_role.get(event_id)
        if not event_role_id:
            return
        event_role = event_guild.get_role(event_role_id)
        logger.info(f"The role {event_role.id} has been deleted for {event_id}.")
        await event_role.delete()

    async def delete_event(self, guild_id: int, event_id: int):
        if not self.event_records.event_to_thread.get(event_id):
            return
        await self.delete_all_rsvp_messages(event_id)
        await self.delete_event_role(guild_id, event_id)
        await self.event_records.remove_event(event_id)

    """ Bot Initialization """

    async def read_from_event_records(self):
        """
        Reads all the prior event records from the event_records.yaml file and adds them to the bot's event records
        """
        with open("./cogs/scheduled_events/event_records.yaml", "r") as f:
            self.event_records = EventRecords(**yaml.safe_load(f))
        if self.event_records.event_to_thread:
            print(f"{len(self.event_records.event_to_thread)} events have been read from event_records.yaml")

    async def read_event_config(self):
        # Initialize the IRL events channel and metroplex roles from configs
        with open("./cogs/scheduled_events/event_config.yaml", "r") as f:
            config = yaml.safe_load(f)
            self.irl_events_channel = self.bot.get_channel(config["irl_events_channel_id"])
            self.metroplex_roles = config["metroplex_roles"]
        print(f"The IRL events channel ID was read as {config['irl_events_channel_id']} from event_config.yaml")
        print(f"The metroplex roles from event_config.yaml were {config['metroplex_roles']}")

    async def add_all_late_roles(self, guild: disnake.Guild, events: List[disnake.GuildScheduledEvent]):
        for event in events:
            role_id = self.event_records.event_to_role.get(event.id)
            if not role_id:
                continue
            event_role = guild.get_role(role_id)
            users = await event.fetch_users()
            for user in users:
                if not user.get_role(role_id):
                    await self.add_role_and_ping_in_thread(event, user)

    async def remind_of_events(self, events: List[disnake.GuildScheduledEvent]):
        bot_owner = self.bot.get_user(self.bot.keys.TEST_SERVER_MOD_ID)
        for event in events:
            if event.id not in self.event_records.event_to_thread.keys():
                event_link = await get_event_link(event.guild_id, event.id)
                await bot_owner.send(f"{event.name} hasn't been announced in the events channel!\n {event_link}")

    @commands.slash_command(name="purge_old_events",
                            description="Purge all the old events that have already been cancelled or deleted")
    async def command_purge_old_events(self, inter: AppCmdInter):
        await self.purge_old_events(inter.guild)

    async def purge_old_events(self, guild):
        events = await guild.fetch_scheduled_events()
        current_event_ids = [event.id for event in events]
        event_record_ids = self.event_records.event_to_thread.keys()
        for event_record_id in event_record_ids:
            if event_record_id not in current_event_ids:
                await self.delete_event(guild.id, event_record_id)


async def get_event_link(guild_id: int, event_id: int) -> str:
    return f"https://discord.com/events/{guild_id}/{event_id}"


async def find_event_id(input_string: str) -> int:
    event_id_regex = r"https:\/\/discord\.com\/events\/\d{18}\/(\d{18})"
    event_id_match = re.search(event_id_regex, input_string)
    if event_id_match:
        return int(event_id_match[1])


async def find_metro_role_id(input_string: str) -> int:
    metro_id_regex = r"<@&(\d{18})>"
    metro_id_match = re.search(metro_id_regex, input_string)
    if metro_id_match:
        return int(metro_id_match[1])


async def create_event_role(event_name: str, guild: disnake.Guild, metro_role_id: int) -> disnake.Role:
    metro_role = guild.get_role(metro_role_id)
    roles = await guild.fetch_roles()
    if event_name in roles:
        raise Exception("Event likely already has a role")

    event_role = await guild.create_role(name=event_name, color=metro_role.color, mentionable=True)
    logger.info(f"**{event_name}** has added the role {event_role.id}.")
    return event_role


async def add_event_role_to_users(event_role: disnake.Role,
                                  event: disnake.GuildScheduledEvent,
                                  metro_role_id: int):
    """
    Create event role and add the role to all event subscribers. Then send the bot help message and add to record.
    """
    event_subscribers = await event.fetch_users()
    for subscriber in event_subscribers:
        await subscriber.add_roles(event_role)
        logger.info(f"The role **{event_role.name}** has been added to {subscriber.display_name} ({subscriber.id})")
    return event_role


async def get_empty_rsvp_embed(event_creator_id, event_name):
    rsvp_embed = (disnake.Embed(title=f"RSVP List for {event_name}")
                  .add_field(name="Going", value=f"<@{event_creator_id}>")
                  .add_field(name="Maybe", value="* *")
                  .add_field(name="Not Going", value="* *"))
    return rsvp_embed


async def get_metroplex_listed(input_string: str):
    metroplex_regex = r"\[((?:DTX)|(?:SATX)|(?:ATX)|(?:HTX)|(?:FW)|(?:CSTAT))\]"
    metro_match = re.search(metroplex_regex, input_string)
    if metro_match:
        return metro_match[1]


def get_key(my_dict, val):
    for key, value in my_dict.items():
        if val == value:
            return key


def setup(bot: SATXBot):
    bot.add_cog(ScheduledEventCog(bot))