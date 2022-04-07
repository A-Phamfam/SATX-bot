import disnake
from disnake import ApplicationCommandInteraction as AppCmdInter
from disnake.ext import commands


class ScheduledEventCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(description="Test command.")
    async def test(self, inter: AppCmdInter):
        await inter.response.send_message("test")
        await inter.channel.send("test2")
        await inter.channel.send("test3")


def setup(bot: commands.Bot):
    bot.add_cog(ScheduledEventCog(bot))
