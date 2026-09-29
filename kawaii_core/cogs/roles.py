import logging
import re
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from kawaii_core.config import CONFIG
from kawaii_core.database.repository import RoleRepository
from kawaii_core.views.role_panel_view import (
    DynamicCategoryRolesView,
    GameRolesView,
    NotificationRolesView,
    RoleMainPanelView,
    extract_emoji_and_label,
)

logger = logging.getLogger("kawaii_bot.roles")


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    roles_group = app_commands.Group(
        name="roles",
        description="Управление интерактивными ролями сервера",
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @roles_group.command(
        name="send",
        description="Отправить панель выбора ролей с папками категорий",
    )
    @app_commands.describe(channel="Канал для отправки панели (по умолчанию текущий)")
    async def send_roles_panel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        if not (member.guild_permissions.manage_roles or member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            await interaction.response.send_message(
                "❌ У вас недостаточно прав для отправки панели ролей (требуется Управление ролями или Управление сервером).",
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Не удалось определить текстовый канал для отправки.",
                ephemeral=True,
            )
            return

        # Загружаем актуальные категории из базы данных
        categories = await RoleRepository.get_categories(guild.id)

        desc_lines = [
            "Добро пожаловать в меню выбора ролей сервера!\n",
            "Нажмите на одну из синих папок ниже, чтобы настроить роли под себя:\n",
        ]
        for cat in categories:
            cat_emoji = cat.get("emoji") or "📁"
            cat_name = cat["name"]
            btns = await RoleRepository.get_category_buttons(cat["id"])
            if btns:
                btn_names = ", ".join(f"`{b['label']}`" for b in btns)
                desc_lines.append(f"{cat_emoji} **{cat_name}** — {btn_names}")
            else:
                desc_lines.append(f"{cat_emoji} **{cat_name}** — *пока нет доступных ролей*")

        desc_lines.append("\n💡 *Меню выбора ролей откроется персонально для вас.*")

        embed = discord.Embed(
            title="🌸 Выбор ролей • Kawaii World",
            description="\n".join(desc_lines),
            color=CONFIG.primary_color,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text="Kawaii World • Система ролей")

        view = RoleMainPanelView(categories=categories)
        await target_channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Панель выбора ролей успешно отправлена в канал {target_channel.mention}!",
            ephemeral=True,
        )

    @app_commands.command(
        name="addcategories",
        description="Создать новую папку для выбора ролей",
    )
    @app_commands.describe(name="Как будет выглядеть название папки (например: Игры, Уведомления, Музыка)")
    @app_commands.default_permissions(manage_roles=True)
    async def add_categories_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        if not (member.guild_permissions.manage_roles or member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            await interaction.response.send_message("❌ Недостаточно прав для управления категориями ролей.", ephemeral=True)
            return

        clean_name = name.strip()
        if not clean_name or len(clean_name) > 50:
            await interaction.response.send_message("❌ Название папки должно быть от 1 до 50 символов.", ephemeral=True)
            return

        existing = await RoleRepository.get_category_by_name(guild.id, clean_name)
        if existing:
            await interaction.response.send_message(
                f"❌ Папка с названием «**{clean_name}**» уже существует на сервере.",
                ephemeral=True,
            )
            return

        # Извлекаем эмодзи из названия, если пользователь передал его в начале (например: "📁 Игры" или "🎮 Гейминг")
        emoji, pure_name = extract_emoji_and_label(clean_name)
        folder_emoji = emoji or "📁"
        folder_name = pure_name if pure_name else clean_name

        cat_id = await RoleRepository.create_category(guild.id, folder_name, emoji=folder_emoji)

        await interaction.response.send_message(
            f"✅ Папка ролей «**{folder_name}**» (ID: `#{cat_id}`) успешно создана!\n\n"
            f"Теперь вы можете добавить в неё роли с помощью команды:\n"
            f"`/addbutton category:\"{folder_name}\" role_id:\"ID_роли\" label:\"Название кнопки\"`",
            ephemeral=True,
        )

    @app_commands.command(
        name="addbutton",
        description="Добавить кнопку выдачи роли в существующую папку",
    )
    @app_commands.describe(
        category="Название уже созданной категории",
        role_id="Айди роли которая будет выдаваться (или упоминание роли)",
        label="Как будет выглядеть в списках (название кнопки, например: CS 2 или 🎮 GTA V)",
    )
    @app_commands.default_permissions(manage_roles=True)
    async def add_button_cmd(
        self,
        interaction: discord.Interaction,
        category: str,
        role_id: str,
        label: str,
    ) -> None:
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        if not (member.guild_permissions.manage_roles or member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            await interaction.response.send_message("❌ Недостаточно прав для добавления кнопок ролей.", ephemeral=True)
            return

        # 1. Поиск категории
        cat = await RoleRepository.get_category_by_name(guild.id, category)
        if not cat:
            await interaction.response.send_message(
                f"❌ Категория «**{category}**» не найдена. Создайте её сначала через `/addcategories`.",
                ephemeral=True,
            )
            return

        # 2. Извлечение и валидация role_id
        digits = re.findall(r"\d+", role_id)
        if not digits:
            await interaction.response.send_message("❌ Укажите корректный ID роли (число) или упоминание роли.", ephemeral=True)
            return

        parsed_role_id = int(digits[0])
        role = guild.get_role(parsed_role_id)
        if not role:
            try:
                role = await guild.fetch_role(parsed_role_id)
            except Exception:
                await interaction.response.send_message(f"❌ Роль с ID `{parsed_role_id}` не найдена на этом сервере.", ephemeral=True)
                return

        # 3. Извлечение эмодзи и очистка названия кнопки
        clean_label = label.strip()
        if not clean_label or len(clean_label) > 80:
            await interaction.response.send_message("❌ Название кнопки должно быть от 1 до 80 символов.", ephemeral=True)
            return

        emoji, final_label = extract_emoji_and_label(clean_label)

        # 4. Сохранение кнопки в БД
        await RoleRepository.add_button(
            category_id=cat["id"],
            role_id=role.id,
            label=final_label,
            emoji=emoji,
        )

        # 5. Проверка иерархии бота
        hierarchy_warning = ""
        if guild.me.top_role <= role:
            hierarchy_warning = (
                f"\n\n⚠️ **Внимание:** наивысшая роль бота ({guild.me.top_role.mention}) находится ниже или равна роли {role.mention}. "
                f"Чтобы бот мог выдавать эту роль участникам, переместите роль бота выше этой роли в Настройках сервера -> Роли."
            )

        display_preview = f"{emoji} {final_label}" if emoji else final_label
        await interaction.response.send_message(
            f"✅ Кнопка для роли {role.mention} успешно добавлена в папку «**{cat['name']}**»!\n"
            f"Вид кнопки в меню: **[{display_preview}]**{hierarchy_warning}",
            ephemeral=True,
        )

    @add_button_cmd.autocomplete("category")
    async def category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return []
        cats = await RoleRepository.get_categories(guild.id)
        return [
            app_commands.Choice(name=c["name"], value=c["name"])
            for c in cats
            if current.lower() in c["name"].lower()
        ][:25]

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """
        Фоновый обработчик кликов для динамических папок и кнопок выдачи ролей.
        Гарантирует работу интерфейса даже после перезагрузки бота.
        """
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if not custom_id or not isinstance(custom_id, str):
            return

        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        # 1. Клик по синей папке категории (role_folder:{category_id})
        if custom_id.startswith("role_folder:"):
            cat_key = custom_id.split(":")[1]

            if cat_key.isdigit():
                cat = await RoleRepository.get_category_by_id(int(cat_key))
            elif cat_key == "games":
                cat = await RoleRepository.get_category_by_name(guild.id, "Игры")
            elif cat_key == "notifications":
                cat = await RoleRepository.get_category_by_name(guild.id, "Уведомления")
            else:
                cat = await RoleRepository.get_category_by_name(guild.id, cat_key)

            if not cat:
                # Если папки еще нет в базе, инициализируем дефолты
                await RoleRepository.ensure_defaults(guild.id)
                cat = await RoleRepository.get_category_by_name(guild.id, "Игры" if cat_key == "games" else "Уведомления")

            if not cat:
                await interaction.response.send_message("❌ Папка не найдена в базе данных.", ephemeral=True)
                return

            buttons = await RoleRepository.get_category_buttons(cat["id"])
            view = DynamicCategoryRolesView(member=member, category=cat, buttons=buttons)
            embed = view.build_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolesCog(bot))
