import disnake
import re
from typing import Union


async def updated_rsvp_embed(original_embed: disnake.Embed, subscriber: disnake.User, category: int):
    embed = original_embed.to_dict()
    for i, field in enumerate(embed['fields']):
        new_field_value = re.sub(f"<@{subscriber.id}>", "", field['value'])
        if new_field_value == "":
            new_field_value = "* *"
        embed['fields'][i]['value'] = new_field_value
    if embed['fields'][category]['value'] == "* *":
        embed['fields'][category]['value'] = f"<@{subscriber.id}>"
    else:
        embed['fields'][category]['value'] = embed['fields'][category]['value'] + f"<@{subscriber.id}>"
    return disnake.Embed.from_dict(embed)


class RsvpView(disnake.ui.View):
    def __init__(self,
                 event: disnake.GuildScheduledEvent,
                 event_thread: disnake.Thread,
                 event_message: Union[disnake.Message, disnake.PartialMessage],
                 subscriber: Union[disnake.Member, disnake.User],
                 event_creator: disnake.User):
        super().__init__(timeout=None)
        self.event = event
        self.event_thread = event_thread
        self.event_message = event_message
        self.subscriber = subscriber
        self.event_creator = event_creator
        self.dm_embed = disnake.Embed(title=f"RSVP to the event: {self.event.name}", description=self.event.description)

    def enable_all_buttons(self):
        self.going.disabled = False
        self.maybe.disabled = False
        self.not_going.disabled = False

    @disnake.ui.button(label="Going", style=disnake.ButtonStyle.green)
    async def going(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.enable_all_buttons()
        self.going.disabled = True

        rsvp_embed = await updated_rsvp_embed(self.event_message.embeds[0], self.subscriber, category=0)
        await self.event_message.edit(content=self.event_message.content, embed=rsvp_embed)

        await inter.response.edit_message(content="You have RSVPed that you are **going**.",
                                          embed=self.dm_embed, view=self)
        if self.event.creator_id != inter.author.id:
            await self.event_creator.send(f"<@{inter.author.id}> is going to {self.event.name}!")

    @disnake.ui.button(label="Maybe", style=disnake.ButtonStyle.grey)
    async def maybe(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.enable_all_buttons()
        self.maybe.disabled = True

        rsvp_embed = await updated_rsvp_embed(self.event_message.embeds[0], self.subscriber, category=1)
        await self.event_message.edit(content=self.event_message.content, embed=rsvp_embed)

        await inter.response.edit_message(content="You have RSVPed that you are **maybe going**.",
                                          embed=self.dm_embed, view=self)
        if self.event.creator_id != inter.author.id:
            await self.event_creator.send(f"<@{inter.author.id}> might be going to {self.event.name}.")

    @disnake.ui.button(label="Not Going", style=disnake.ButtonStyle.red)
    async def not_going(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.enable_all_buttons()
        self.not_going.disabled = True

        rsvp_embed = await updated_rsvp_embed(self.event_message.embeds[0], self.subscriber, category=2)
        await self.event_message.edit(content=self.event_message.content, embed=rsvp_embed)

        await inter.response.edit_message(content="You have RSVPed that you are **not going**.",
                                          embed=self.dm_embed, view=self)
        if self.event.creator_id != inter.author.id:
            await self.event_creator.send(f"<@{inter.author.id}> is not going to {self.event.name} :(")

