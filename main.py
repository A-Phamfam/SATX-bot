import disnake
from disnake.ext.commands import Bot
from cogs import cogs_to_include
from datetime import datetime
from dataclasses import dataclass
import yaml


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


if __name__ == '__main__':
    intents = disnake.Intents.default()
    # intents.members = True  # turn on privileged members intent

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
