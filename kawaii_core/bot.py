import logging
from typing import List
import discord
from discord import app_commands
from discord.ext import commands

from kawaii_core.config import CONFIG
from kawaii_core.database.connection import db_manager

logger = logging.getLogger("kawaii_bot")


class KawaiiBot(commands.Bot):
    COGS: List[str] = [
        "kawaii_core.cogs.profile",
        "kawaii_core.cogs.warns",
        "kawaii_core.cogs.guard",
        "kawaii_core.cogs.permissions",
        "kawaii_core.cogs.staff_list",
        "kawaii_core.cogs.recruitment",
        "kawaii_core.cogs.roles",
        "kawaii_core.cogs.events",
    ]

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        logger.info("Initializing database...")
        await db_manager.initialize()
        logger.info("Database schema synchronized successfully.")

        logger.info("Loading extensions...")
        for cog in self.COGS:
            try:
                await self.load_extension(cog)
                logger.info("Extension %s loaded successfully.", cog)
            except Exception as exc:
                logger.error("Failed to load extension %s: %s", cog, exc, exc_info=True)

        from kawaii_core.cogs.recruitment import StaffRecruitmentPanelView
        self.add_view(StaffRecruitmentPanelView())

        from kawaii_core.views.role_panel_view import RolePanelView
        self.add_view(RolePanelView())

        self.loop.create_task(self._sync_commands())

    async def _sync_commands(self) -> None:
        await self.wait_until_ready()
        try:
            logger.info("Synchronizing application command tree for guild %d...", CONFIG.guild_id)
            guild_obj = discord.Object(id=CONFIG.guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            logger.info("Application command tree synchronized (%d commands) for guild %d.", len(synced), CONFIG.guild_id)
            # Очищаем глобальные команды, чтобы Discord не дублировал команды (когда одна версия рабочая, а другая нет)
            try:
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                logger.info("Global commands cleared to prevent duplicates in Discord.")
            except Exception as glob_err:
                logger.warning("Could not clear global commands: %s", glob_err)
        except discord.Forbidden:
            logger.warning(
                "Missing Access (403) when syncing commands to guild %d. "
                "Make sure the bot is invited with 'applications.commands' scope! "
                "Syncing globally instead...",
                CONFIG.guild_id,
            )
            synced = await self.tree.sync()
            logger.info("Application command tree synchronized globally (%d commands).", len(synced))
        except Exception as exc:
            logger.error("Error during command tree sync: %s", exc, exc_info=True)

    async def on_ready(self) -> None:
        if self.user:
            logger.info("Logged in as %s (ID: %s)", self.user.name, self.user.id)
            logger.info("Connected to %d guilds.", len(self.guilds))
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Kawaii World • /profile",
                )
            )

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Команда на перезарядке. Подождите еще {error.retry_after:.1f} сек."
        elif isinstance(error, app_commands.MissingPermissions):
            msg = "❌ У вас недостаточно прав для выполнения этой команды."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "❌ У бота недостаточно прав для выполнения этой команды."
        else:
            logger.error("Unhandled slash command error: %s", error, exc_info=True)
            msg = "❌ Произошла непредвиденная ошибка при выполнении команды."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
