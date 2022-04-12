import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands, tasks


class ScheduledEventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guilds = []
        self.events = []

    @tasks.loop(minutes=10.0)
    async def check_for_scheduled_events(self):
        self.bot.fetch_guilds()


def setup(bot: commands.Bot):
    bot.add_cog(ScheduledEventCog(bot))
