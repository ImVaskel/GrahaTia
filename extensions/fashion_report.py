"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING, ClassVar

import discord
from discord.ext import commands

from utilities._types.xiv.reddit.kaiyoko import TopLevelListingResponse
from utilities.cache import cache
from utilities.cog import GrahaBaseCog as BaseCog
from utilities.containers.event_subscription import EventSubConfig
from utilities.context import Context as BaseContext
from utilities.formats import plural


if TYPE_CHECKING:
    from bot import Graha

FASHION_REPORT_PATTERN: re.Pattern[str] = re.compile(
    r"Fashion Report - Full Details - For Week of (?P<date>[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}) \(Week (?P<week_num>[0-9]{3})\)"
)


class Context(BaseContext):
    subscription_config: EventSubConfig


class FashionReport(BaseCog):
    FASHION_REPORT_START: ClassVar[datetime.datetime] = datetime.datetime(
        year=2018,
        month=1,
        day=26,
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=datetime.timezone.utc,
    )

    def __init__(self, bot: Graha) -> None:
        super().__init__(bot)

    async def cog_before_invoke(self, ctx: Context) -> None:
        config: EventSubConfig = await self._get_subscription_config(ctx)  # type: ignore # gay with instance bindings
        ctx.subscription_config = config

    @cache()
    async def _get_subscription_config(self, ctx: Context) -> EventSubConfig:
        assert ctx.guild

        record = await self.bot.get_sub_config(ctx)

        if record:
            return EventSubConfig.from_record(self.bot, record=record)

        return EventSubConfig(self.bot, guild_id=ctx.guild.id)

    def weeks_since_start(self, dt: datetime.datetime) -> int:
        td = dt - self.FASHION_REPORT_START

        seconds = round(td.total_seconds())
        weeks, _ = divmod(seconds, 60 * 60 * 24 * 7)

        return weeks

    def humanify_delta(self, *, td: datetime.timedelta, format: str) -> str:
        seconds = round(td.total_seconds())

        days, seconds = divmod(seconds, 60 * 60 * 24)
        hours, seconds = divmod(seconds, 60 * 60)
        minutes, seconds = divmod(seconds, 60)

        return f"{format.title()} in {plural(days):day}, {plural(hours):hour}, {plural(minutes):minute} and {plural(seconds):second}."

    async def get_kaiyoko_submissions(self) -> TopLevelListingResponse:
        headers = {"User-Agent": "Graha Discord Bot (by /u/AbstractUmbra)"}
        async with self.bot.session.get("https://reddit.com/user/kaiyoko/submitted.json", headers=headers) as resp:
            data: TopLevelListingResponse = await resp.json()

        return data

    async def filter_submissions(self, now: datetime.datetime | None = None, /) -> tuple[str, str, str, discord.Colour]:
        submissions = await self.get_kaiyoko_submissions()

        for submission in submissions["data"]["children"]:
            if match := FASHION_REPORT_PATTERN.search(submission["data"]["title"]):
                now = now or datetime.datetime.now(datetime.timezone.utc)
                if not self.weeks_since_start(now) == int(match["week_num"]):
                    continue

                created = datetime.datetime.fromtimestamp(submission["data"]["created_utc"], tz=datetime.timezone.utc)
                if (now - created) > datetime.timedelta(days=7):
                    continue

                if 0 < now.weekday() < 4:
                    delta = datetime.timedelta((4 - now.weekday()) % 7)
                    fmt = "Available"
                    colour = discord.Colour.green()
                else:
                    delta = datetime.timedelta((0 - now.weekday()) % 7)
                    fmt = "Resets"
                    colour = discord.Colour.dark_orange()

                upcoming_event = now + delta
                upcoming_event = upcoming_event.replace(hour=8, minute=0, second=0, microsecond=0)
                reset_str = self.humanify_delta(td=(upcoming_event - now), format=fmt)

                return (
                    f"Fashion Report details for week of {match['date']} (Week {match['week_num']})",
                    reset_str,
                    submission["data"]["url"],
                    colour,
                )

        raise ValueError("Unabled to fetch the reddit post details.")

    async def _gen_fashion_embed(self, now: datetime.datetime | None = None, /) -> discord.Embed:
        prose, reset, url, colour = await self.filter_submissions(now)

        embed = discord.Embed(title=prose, url=url, colour=colour)
        embed.description = reset
        embed.set_image(url=url)

        return embed

    @commands.command(name="fashionreport", aliases=["fr", "fashion-report"])
    async def fashion_report(self, ctx: Context) -> None:
        """Fetch the latest fashion report data from /u/Kaiyoko."""
        try:
            embed = await self._gen_fashion_embed()
        except ValueError:
            embed = discord.Embed(description="Seems the post for this week isn't up yet.")

        await ctx.send(embed=embed)

    async def _add_subscription(self, ctx: Context, /) -> None:
        current_config = ctx.subscription_config
        if current_config.webhook_url is None:
            # create webhook
            pass
        # TODO: add record, create webhook if not exists.

    async def _remove_subscription(self) -> None:
        current_config: EventSubConfig = await self._get_subscription_config(ctx=ctx)  # type: ignore # typing is bad with instance bindings
        # TODO: delete record

    @commands.command()
    async def fashion_report_subscribe(self, ctx: Context, channel: discord.TextChannel | None) -> None:
        current_config = ctx.subscription_config

        if current_config.subscriptions.fashion_report:
            await self._remove_subscription()
            await ctx.send("You have now unsubscribed from fashion report notifications for this server.")
            return

        await self._add_subscription(ctx)
        await ctx.send("You have now subscribed to fashion report notifications for this server, in this channel.")


async def setup(bot: Graha) -> None:
    await bot.add_cog(FashionReport(bot))
