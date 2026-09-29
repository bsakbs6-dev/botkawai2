from datetime import datetime, timedelta, timezone
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from kawaii_core.config import CONFIG, RECRUITMENT_BANNER_PATH
from kawaii_core.database.repository import RecruitmentRepository, StaffRepository
from kawaii_core.domain.enums import BranchType, PositionRank
from kawaii_core.domain.hierarchy import HierarchyService
from kawaii_core.services.staff_service import StaffService


class StaffApplicationModal(discord.ui.Modal):
    def __init__(self, branch: BranchType, user_id: int):
        super().__init__(title=f"Заявка на {branch.value}")
        self.branch = branch
        self.user_discord_id.default = str(user_id)

    name_age_tz = discord.ui.TextInput(
        label="1. Имя, возраст, ник и часовой пояс",
        placeholder="Имя, возраст, основной ник в Discord и часовой пояс",
        required=True,
        max_length=150,
    )
    user_discord_id = discord.ui.TextInput(
        label="2. Ваш ID в дискорде",
        placeholder="Ваш цифровой ID в Discord",
        required=True,
        max_length=30,
    )
    motivation = discord.ui.TextInput(
        label="3. Почему хотите стать staff команды?",
        style=discord.TextStyle.paragraph,
        placeholder="Почему вы хотите стать staff команды нашего сервера?",
        required=True,
        max_length=600,
    )
    rules_and_activity = discord.ui.TextInput(
        label="4. Правила сервера и время активности",
        style=discord.TextStyle.paragraph,
        placeholder="Знакомство с правилами? Сколько часов в день? В какое время активны?",
        required=True,
        max_length=600,
    )
    experience_and_status = discord.ui.TextInput(
        label="5. Опыт модерации и статус в стаффе",
        style=discord.TextStyle.paragraph,
        placeholder="Опыт на других серверах (на каких)? Состоите ли сейчас в стафф-команде?",
        required=True,
        max_length=600,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Заявку можно подать только на сервере.", ephemeral=True)
            return

        user_id = interaction.user.id

        # 1. Проверка ЧСКП
        if await StaffRepository.is_user_blacklisted(guild.id, user_id):
            await interaction.followup.send(
                "❌ Вы находитесь в Черном Списке Команды Проекта (ЧСКП) и не можете подавать заявки.",
                ephemeral=True,
            )
            return

        # 2. Проверка, состоит ли уже в стаффе
        if isinstance(interaction.user, discord.Member):
            profile = HierarchyService.resolve_profile(interaction.user)
            if profile.is_staff and profile.branch != BranchType.NONE:
                await interaction.followup.send(
                    f"❌ Вы уже состоите в команде проекта на ветке **{profile.branch.value}** ({profile.position_title}).",
                    ephemeral=True,
                )
                return

        # 3. Проверка на активную заявку на рассмотрении
        pending_app = await RecruitmentRepository.get_pending_application(user_id)
        if pending_app:
            await interaction.followup.send(
                f"❌ У вас уже есть активная заявка на рассмотрении (ветка **{pending_app['branch']}**). "
                "Дождитесь решения по текущей заявке перед подачей новой.",
                ephemeral=True,
            )
            return

        # 4. Проверка кулдауна 7 дней при отклонении
        last_rejected = await RecruitmentRepository.get_last_rejected_application(user_id)
        if last_rejected and last_rejected.get("closed_at"):
            try:
                closed_dt = datetime.fromisoformat(last_rejected["closed_at"])
                if closed_dt.tzinfo is None:
                    closed_dt = closed_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if (now_utc - closed_dt) < timedelta(days=7):
                    unblock_ts = int((closed_dt + timedelta(days=7)).timestamp())
                    await interaction.followup.send(
                        f"❌ Ваша предыдущая заявка была отклонена. "
                        f"Подать новую заявку можно только через 7 дней (<t:{unblock_ts}:R>, <t:{unblock_ts}:d>).",
                        ephemeral=True,
                    )
                    return
            except Exception:
                pass

        now = datetime.now(timezone.utc)

        # 5. Сохранение заявки в БД
        app_id = await RecruitmentRepository.create_application(
            guild_id=guild.id,
            user_id=user_id,
            discord_id_input=self.user_discord_id.value.strip(),
            branch=self.branch.value,
            name_age_tz=self.name_age_tz.value.strip(),
            activity=self.rules_and_activity.value.strip(),
            rules_score="—",
            experience=self.experience_and_status.value.strip(),
            motivation=self.motivation.value.strip(),
            created_at=now,
        )

        # 6. Отправка в канал заявок
        target_channel = guild.get_channel(CONFIG.recruitment_channel_id)
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                "⚠️ Заявка сохранена, но канал для рассмотрения заявок не найден. Пожалуйста, сообщите администрации.",
                ephemeral=True,
            )
            return

        # Определяем роль для пинга кураторов ветки ("Отвечает | ...")
        branch_cfg = StaffService._get_branch_config(self.branch)
        qualifier_role_id = branch_cfg.master_qualifier_role_id if branch_cfg else None
        ping_text = f"<@&{qualifier_role_id}>" if qualifier_role_id else f"@Staff ({self.branch.value})"

        embed = discord.Embed(
            title=f"📋 Новая заявка в стафф • #{app_id}",
            color=CONFIG.primary_color,
            timestamp=now,
        )
        if interaction.user.display_avatar:
            embed.set_author(
                name=f"{interaction.user.display_name} ({interaction.user.name})",
                icon_url=interaction.user.display_avatar.url,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.add_field(name="👤 Кандидат", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        embed.add_field(name="🌿 Желаемая ветка", value=f"**{self.branch.value}**", inline=True)
        embed.add_field(name="📅 Дата подачи", value=f"<t:{int(now.timestamp())}:F>", inline=False)

        embed.add_field(
            name="1. Имя, возраст, основной ник в Discord и часовой пояс",
            value=f"```{self.name_age_tz.value.strip()}```",
            inline=False,
        )
        embed.add_field(
            name="2. Ваш ID в дискорде",
            value=f"`{self.user_discord_id.value.strip()}` ({interaction.user.mention})",
            inline=False,
        )
        embed.add_field(
            name="3. Почему вы хотите стать staff команды нашего сервера?",
            value=f"```{self.motivation.value.strip()}```",
            inline=False,
        )
        embed.add_field(
            name="4-6. Правила сервера, время в день и часы активности",
            value=f"```{self.rules_and_activity.value.strip()}```",
            inline=False,
        )
        embed.add_field(
            name="7-8. Опыт модерации и статус в стафф-команде",
            value=f"```{self.experience_and_status.value.strip()}```",
            inline=False,
        )

        view = StaffApplicationControlView(app_id=app_id)
        msg = await target_channel.send(content=f"🔔 {ping_text}", embed=embed, view=view)

        await RecruitmentRepository.set_message_info(
            app_id=app_id,
            channel_id=target_channel.id,
            message_id=msg.id,
        )

        await interaction.followup.send(
            f"✅ Ваша заявка на ветку **{self.branch.value}** успешно отправлена на рассмотрение руководству! "
            f"Ожидайте ответа в личные сообщения.",
            ephemeral=True,
        )


class RecruitmentRoleInfoView(discord.ui.View):
    def __init__(self, branch: BranchType):
        super().__init__(timeout=300)
        self.branch = branch

    @discord.ui.button(
        label="Отправить заявку",
        style=discord.ButtonStyle.primary,
        emoji="📝",
    )
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user_id = interaction.user.id
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Действие доступно только на сервере.", ephemeral=True)
            return

        # 1. Проверка ЧСКП
        if await StaffRepository.is_user_blacklisted(guild.id, user_id):
            await interaction.response.send_message(
                "❌ Вы находитесь в Черном Списке Команды Проекта (ЧСКП) и не можете подавать заявки.",
                ephemeral=True,
            )
            return

        # 2. Проверка текущего стаффа
        if isinstance(interaction.user, discord.Member):
            profile = HierarchyService.resolve_profile(interaction.user)
            if profile.is_staff and profile.branch != BranchType.NONE:
                await interaction.response.send_message(
                    f"❌ Вы уже состоите в команде проекта на ветке **{profile.branch.value}** ({profile.position_title}).",
                    ephemeral=True,
                )
                return

        # 3. Проверка активной заявки
        pending_app = await RecruitmentRepository.get_pending_application(user_id)
        if pending_app:
            await interaction.response.send_message(
                f"❌ У вас уже есть активная заявка на рассмотрении (ветка **{pending_app['branch']}**). "
                "Дождитесь решения по текущей заявке перед подачей новой.",
                ephemeral=True,
            )
            return

        # 4. Проверка кулдауна 7 дней при отклонении
        last_rejected = await RecruitmentRepository.get_last_rejected_application(user_id)
        if last_rejected and last_rejected.get("closed_at"):
            try:
                closed_dt = datetime.fromisoformat(last_rejected["closed_at"])
                if closed_dt.tzinfo is None:
                    closed_dt = closed_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if (now_utc - closed_dt) < timedelta(days=7):
                    unblock_ts = int((closed_dt + timedelta(days=7)).timestamp())
                    await interaction.response.send_message(
                        f"❌ Ваша предыдущая заявка была отклонена. "
                        f"Подать новую заявку можно только через 7 дней (<t:{unblock_ts}:R>, <t:{unblock_ts}:d>).",
                        ephemeral=True,
                    )
                    return
            except Exception:
                pass

        # Открываем форму с предзаполненным ID
        modal = StaffApplicationModal(branch=self.branch, user_id=interaction.user.id)
        await interaction.response.send_modal(modal)


class RecruitmentBranchSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Moderator",
                value=BranchType.MODERATION.value,
                description="Следить за порядком в чатах и голосовых каналах",
                emoji="🛡️",
            ),
            discord.SelectOption(
                label="Support",
                value=BranchType.SUPPORT.value,
                description="Помогать новичкам и отвечать на вопросы пользователей",
                emoji="💬",
            ),
            discord.SelectOption(
                label="Eventer",
                value=BranchType.EVENTERS.value,
                description="Организовывать и проводить мероприятия и игры",
                emoji="🎉",
            ),
        ]
        super().__init__(
            placeholder="Выберите желаемую должность для подачи заявки...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="staff_recruitment:branch_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_value = self.values[0]
        branch = BranchType(selected_value)

        branch_details = {
            BranchType.MODERATION: {
                "title": "Набор на роль Moderator",
                "role_display": "@・Moderator",
                "task": "следят за соблюдением порядка и правил сервера в голосовых каналах и чатах, а также оперативно разбирают жалобы от пользователей.",
            },
            BranchType.SUPPORT: {
                "title": "Набор на роль Support",
                "role_display": "@・Support",
                "task": "активно оказывают помощь пользователям сервера, отвечая на их вопросы, и помогают освоиться новым участникам.",
            },
            BranchType.EVENTERS: {
                "title": "Набор на роль Eventer",
                "role_display": "@・Eventer",
                "task": "организуют и проводят увлекательные мероприятия, конкурсы и игры на сервере, заботясь о хорошем настроении участников.",
            },
        }

        details = branch_details.get(
            branch,
            {
                "title": f"Набор на роль {branch.value}",
                "role_display": f"@・{branch.value}",
                "task": "выполняют обязанности команды проекта.",
            },
        )

        embed = discord.Embed(
            title=f"🌸 {details['title']}",
            color=CONFIG.primary_color,
        )

        embed.description = (
            f"`{details['role_display']}` — {details['task']}\n\n"
            f"**Требования!**\n"
            f"• **Ответственность:** способность принимать взвешенные решения и реагировать на нарушения правил сервера.\n"
            f"• **Активность:** готовность проводить время на сервере, следить за чатами и каналами.\n"
            f"• **Коммуникабельность:** хорошие навыки общения и работа в команде.\n"
            f"• **Знание правил:** хорошее понимание правил сервера и готовность их соблюдать и обеспечивать их соблюдение другими участниками.\n\n"
            f"*Если вы подходите под требования, нажмите кнопку **«Отправить заявку»** ниже и заполните анкету!*"
        )

        view = RecruitmentRoleInfoView(branch=branch)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class StaffRecruitmentPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RecruitmentBranchSelect())


class StaffApplicationControlView(discord.ui.View):
    def __init__(self, app_id: int):
        super().__init__(timeout=None)
        self.app_id = app_id

        self.accept_button.custom_id = f"staff_app:accept:{app_id}"
        self.reject_button.custom_id = f"staff_app:reject:{app_id}"

    @discord.ui.button(
        label="Принять",
        style=discord.ButtonStyle.success,
        emoji="✅",
    )
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass  # Обрабатывается в Cog on_interaction для персистентности

    @discord.ui.button(
        label="Отклонить",
        style=discord.ButtonStyle.danger,
        emoji="❌",
    )
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass  # Обрабатывается в Cog on_interaction для персистентности


class RecruitmentCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if not custom_id or not isinstance(custom_id, str):
            return

        if not custom_id.startswith("staff_app:"):
            return

        parts = custom_id.split(":")
        if len(parts) != 3:
            return

        action, app_id_str = parts[1], parts[2]
        if not app_id_str.isdigit():
            return

        app_id = int(app_id_str)
        app = await RecruitmentRepository.get_application(app_id)
        if not app:
            await interaction.response.send_message("❌ Заявка не найдена в базе данных.", ephemeral=True)
            return

        if app["status"] != "pending":
            await interaction.response.send_message("ℹ️ Эта заявка уже была рассмотрена ранее.", ephemeral=True)
            return

        reviewer = interaction.user
        if not isinstance(reviewer, discord.Member):
            return

        target_branch = BranchType(app["branch"])
        reviewer_profile = HierarchyService.resolve_profile(reviewer)

        # Проверка прав: только Мастер и выше нужной ветки, либо Стафф Админ / Владелец
        is_supreme_lead = reviewer_profile.is_supreme or reviewer_profile.rank >= PositionRank.STAFF_ADMIN
        is_branch_master = (
            reviewer_profile.rank >= PositionRank.MASTER
            and reviewer_profile.branch == target_branch
        )

        if not (is_supreme_lead or is_branch_master):
            await interaction.response.send_message(
                f"❌ Рассматривать заявки ветки **{target_branch.value}** могут только Мастера этой ветки и выше.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        now = datetime.now(timezone.utc)
        candidate_id = app["user_id"]
        guild = interaction.guild

        candidate = guild.get_member(candidate_id) if guild else None
        if not candidate and guild:
            try:
                candidate = await guild.fetch_member(candidate_id)
            except Exception:
                pass

        created_dt = datetime.fromisoformat(app["created_at"])
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)

        dm_delivered = False

        if action == "accept":
            await RecruitmentRepository.update_application_status(
                app_id=app_id,
                status="accepted",
                reviewer_id=reviewer.id,
                closed_at=now,
            )

            # Отправка ЛС кандидату
            management_names = {
                BranchType.MODERATION: "модерации",
                BranchType.SUPPORT: "саппортов",
                BranchType.EVENTERS: "эвентеров",
            }
            mgmt_title = management_names.get(target_branch, target_branch.value)

            dm_embed = discord.Embed(
                title="✨ Ваша заявка одобрена • Kawaii World",
                description=f"Поздравляем! Ваша заявка на вступление в команду проекта на ветку **{target_branch.value}** была **одобрена**!",
                color=CONFIG.success_color,
                timestamp=now,
            )
            if guild and guild.icon:
                dm_embed.set_thumbnail(url=guild.icon.url)

            dm_embed.add_field(name="📅 Заявка была подана", value=f"<t:{int(created_dt.timestamp())}:F>", inline=True)
            dm_embed.add_field(name="✅ Заявку одобрили в", value=f"<t:{int(now.timestamp())}:F>", inline=True)
            dm_embed.add_field(name="🛡️ Заявку одобрил", value=f"{reviewer.mention} (`{reviewer.display_name}`)", inline=False)
            dm_embed.add_field(
                name="📋 Дальнейшие инструкции",
                value=(
                    f"Ожидайте, из управления **{mgmt_title}** вам напишут в личные сообщения и назначат собеседование.\n"
                    f"⏳ **Время ожидания:** до 24 часов.\n\n"
                    f"⚠️ *Пожалуйста, убедитесь, что ваши личные сообщения открыты для участников сервера!*"
                ),
                inline=False,
            )
            if guild:
                dm_embed.set_footer(text=f"{guild.name} • Recruitment System")

            if candidate:
                try:
                    await candidate.send(embed=dm_embed)
                    dm_delivered = True
                except Exception:
                    dm_delivered = False

            # Обновление сообщения в канале
            if interaction.message:
                orig_embed = interaction.message.embeds[0] if interaction.message.embeds else None
                if orig_embed:
                    orig_embed.color = CONFIG.success_color
                    orig_embed.add_field(
                        name="✅ Статус заявки",
                        value=f"**Одобрена** модератором {reviewer.mention} (<t:{int(now.timestamp())}:R>)",
                        inline=False,
                    )
                # Отключаем кнопки
                disabled_view = discord.ui.View()
                disabled_view.add_item(
                    discord.ui.Button(label="Одобрено", style=discord.ButtonStyle.success, emoji="✅", disabled=True)
                )
                await interaction.message.edit(embed=orig_embed, view=disabled_view)

            dm_info = "уведомление успешно доставлено в ЛС" if dm_delivered else "у кандидата закрыты ЛС, уведомление не доставлено"
            await interaction.followup.send(
                f"✅ Заявка #{app_id} одобрена модератором {reviewer.mention} ({dm_info}).",
                ephemeral=True,
            )

        elif action == "reject":
            await RecruitmentRepository.update_application_status(
                app_id=app_id,
                status="rejected",
                reviewer_id=reviewer.id,
                closed_at=now,
            )

            unblock_ts = int((now + timedelta(days=7)).timestamp())

            dm_embed = discord.Embed(
                title="🥀 Ваша заявка отклонена • Kawaii World",
                description=f"Ваша заявка на вступление в команду проекта на ветку **{target_branch.value}** была отклонена руководством.",
                color=CONFIG.danger_color,
                timestamp=now,
            )
            if guild and guild.icon:
                dm_embed.set_thumbnail(url=guild.icon.url)

            dm_embed.add_field(name="📅 Заявка была подана", value=f"<t:{int(created_dt.timestamp())}:F>", inline=True)
            dm_embed.add_field(name="⏳ Заявка была отклонена", value=f"<t:{int(now.timestamp())}:F>", inline=True)
            dm_embed.add_field(name="🛡️ Проверил", value=f"{reviewer.mention} (`{reviewer.display_name}`)", inline=False)
            dm_embed.add_field(
                name="⏱️ Повторная подача",
                value=f"Новую заявку вы сможете подать через **7 дней** (<t:{unblock_ts}:d>, <t:{unblock_ts}:R>).",
                inline=False,
            )
            if guild:
                dm_embed.set_footer(text=f"{guild.name} • Recruitment System")

            if candidate:
                try:
                    await candidate.send(embed=dm_embed)
                    dm_delivered = True
                except Exception:
                    dm_delivered = False

            # Обновление сообщения в канале
            if interaction.message:
                orig_embed = interaction.message.embeds[0] if interaction.message.embeds else None
                if orig_embed:
                    orig_embed.color = CONFIG.danger_color
                    orig_embed.add_field(
                        name="❌ Статус заявки",
                        value=f"**Отклонена** модератором {reviewer.mention} (<t:{int(now.timestamp())}:R>)",
                        inline=False,
                    )
                disabled_view = discord.ui.View()
                disabled_view.add_item(
                    discord.ui.Button(label="Отклонено", style=discord.ButtonStyle.danger, emoji="❌", disabled=True)
                )
                await interaction.message.edit(embed=orig_embed, view=disabled_view)

            dm_info = "уведомление успешно доставлено в ЛС" if dm_delivered else "у кандидата закрыты ЛС, уведомление не доставлено"
            await interaction.followup.send(
                f"❌ Заявка #{app_id} отклонена модератором {reviewer.mention} ({dm_info}).",
                ephemeral=True,
            )

    @app_commands.command(
        name="setup_staff_panel",
        description="Отправить панель набора в команду проекта (стафф)",
    )
    @app_commands.describe(channel="Канал для отправки панели (по умолчанию текущий)")
    async def setup_staff_panel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        invoker = interaction.user
        if not isinstance(invoker, discord.Member):
            return

        invoker_profile = HierarchyService.resolve_profile(invoker)
        if not (invoker_profile.is_supreme or invoker_profile.rank >= PositionRank.STAFF_ADMIN):
            await interaction.response.send_message(
                "❌ Настройка панели набора доступна только Владельцу и Стафф Администратору.",
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Не удалось определить текстовый канал для отправки панели.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="🌸 Набор в команду проекта • Kawaii World",
            description=(
                "Вы проводите время на нашем сервере и стремитесь стать частью нашей команды? "
                "Нажав на кнопку ниже, у вас есть возможность выбрать одну из доступных ролей, "
                "получить более детальную информацию о каждой и подать свою заявку!"
            ),
            color=CONFIG.primary_color,
        )

        file = None
        if RECRUITMENT_BANNER_PATH.exists():
            file = discord.File(str(RECRUITMENT_BANNER_PATH), filename="staff_recruitment_banner.jpg")
            embed.set_image(url="attachment://staff_recruitment_banner.jpg")

        view = StaffRecruitmentPanelView()

        if file:
            await target_channel.send(embed=embed, file=file, view=view)
        else:
            await target_channel.send(embed=embed, view=view)

        await interaction.followup.send(
            f"✅ Панель набора в стафф успешно отправлена в канал {target_channel.mention}!",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RecruitmentCog(bot))
