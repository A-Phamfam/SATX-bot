import sys
from typing import Any
import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext.commands import Bot, errors, Context
from cogs import cogs_to_include
from datetime import datetime
from dataclasses import dataclass
import yaml
from util import logger
import traceback


@dataclass
class Keys:
    """
    Class to contain the secret keys in the SECRETS.yaml
    """
    BOT_TOKEN: str
    BOT_ID: int
    BOT_OWNER_ID: int
    BOT_NAME: str
    BOT_PREFIX: str
    TEST_SERVER_ID: int
    TEST_SERVER_MOD_ID: int

def fancy_traceback(exc: Exception) -> str:
    """May not fit the message content limit"""
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return f"```py\n{text[-4086:]}\n```"

class SATXBot(Bot):
    """
    Main discord bot instance.
    """

    def __init__(self, bot_prefix: str, t_keys: Keys, **settings):
        super(Bot, self).__init__(bot_prefix, **settings)
        self.keys = t_keys
        for cog in cogs_to_include:
            self.load_extension(f"cogs.{cog}")

        self.run(self.keys.BOT_TOKEN)

    async def on_ready(self):
        print(f"{self.keys.BOT_NAME} is now ready at {datetime.now()}.\n"
              f"{self.keys.BOT_NAME} is now active in test guild {self.keys.TEST_SERVER_ID}.")

    async def notify_bot_owner(self, error):
        embed = disnake.Embed(
            title="Error",
            description=fancy_traceback(error),
            color=disnake.Color.red(),
        )
        await self.get_user(self.keys.BOT_OWNER_ID).send(embed=embed)
        logger.warning(fancy_traceback(error))

    async def on_slash_command_error(
            self, interaction: ApplicationCommandInteraction, exception: errors.CommandError
    ) -> None:
        await self.notify_bot_owner(exception)

    async def on_message_command_error(self,
                                       inter: ApplicationCommandInteraction,
                                       error: errors.CommandError,
                                       ) -> None:
        await self.notify_bot_owner(error)

    async def on_message_command_error(
            self, interaction: ApplicationCommandInteraction, exception: errors.CommandError
    ) -> None:
        await self.notify_bot_owner(exception)

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        await self.notify_bot_owner(sys.exc_info()[1])


if __name__ == '__main__':
    intents = disnake.Intents.default()
    intents.members = True  # turn on privileged members intent

    with open("SECRET.yaml", "r") as secret:
        keys = Keys(**yaml.safe_load(secret))

    options = {
        "case_insensitive": True,
        "owner_id": keys.BOT_OWNER_ID,
        "intents": intents,
        "test_guilds": [keys.TEST_SERVER_ID],
        "sync_commands_debug": True
    }

    bot = SATXBot(keys.BOT_PREFIX, keys, **options)
