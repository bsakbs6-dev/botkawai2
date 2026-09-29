from datetime import datetime, timezone
from typing import Optional
import discord

from kawaii_core.config import CONFIG
from kawaii_core.domain.enums import BranchType, PositionRank


class AuditLogger:
    @staticmethod
    def _create_base_embed(title: str, color: int = CONFIG.primary_color) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Kawaii World • Staff Audit", icon_url=None)
        return embed

    @classmethod
    async def log_promotion(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        old_rank: PositionRank,
        new_rank: PositionRank,
        branch: BranchType,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("📈 Повышение сотрудника", color=CONFIG.success_color)
        embed.add_field(name="Сотрудник", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Модератор", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Ветка", value=branch.value, inline=True)
        embed.add_field(name="Прежняя должность", value=old_rank.display_name, inline=True)
        embed.add_field(name="Новая должность", value=new_rank.display_name, inline=True)
        await channel.send(embed=embed)

    @classmethod
    async def log_demotion(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        old_rank: PositionRank,
        new_rank: PositionRank,
        branch: BranchType,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("📉 Понижение сотрудника", color=CONFIG.danger_color)
        embed.add_field(name="Сотрудник", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Модератор", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Ветка", value=branch.value, inline=True)
        embed.add_field(name="Прежняя должность", value=old_rank.display_name, inline=True)
        embed.add_field(name="Новая должность", value=new_rank.display_name, inline=True)
        await channel.send(embed=embed)

    @classmethod
    async def log_appointment(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        branch: BranchType,
        position_name: str,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("✨ Назначение в стафф", color=CONFIG.success_color)
        embed.add_field(name="Сотрудник", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Назначил", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Ветка", value=branch.value, inline=True)
        embed.add_field(name="Должность", value=position_name, inline=True)
        await channel.send(embed=embed)

    @classmethod
    async def log_dismissal(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("🚪 Снятие со стаффа", color=CONFIG.danger_color)
        embed.add_field(name="Сотрудник", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Инициатор", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        if reason:
            embed.add_field(name="Причина", value=reason, inline=False)
        await channel.send(embed=embed)

    @classmethod
    async def log_warn(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        reason: str,
        expires_at: datetime,
        active_count: int,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("⚠️ Выдача выговора", color=CONFIG.danger_color)
        embed.add_field(name="Сотрудник", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Выдал", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Активных выговоров", value=f"`{active_count}/{CONFIG.max_active_warns}`", inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(
            name="Авто-снятие",
            value=f"<t:{int(expires_at.timestamp())}:f> (<t:{int(expires_at.timestamp())}:R>)",
            inline=False,
        )
        await channel.send(embed=embed)

    @classmethod
    async def log_unwarn(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        reason: str,
        active_count: int,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("🛡️ Снятие выговора", color=CONFIG.success_color)
        embed.add_field(name="Сотрудник", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Снял", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Осталось выговоров", value=f"`{active_count}/{CONFIG.max_active_warns}`", inline=True)
        embed.add_field(name="Причина снятия", value=reason, inline=False)
        await channel.send(embed=embed)

    @classmethod
    async def log_warn_expired(cls, guild: discord.Guild, target_id: int, reason: str) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("⏳ Выговор истек по сроку", color=0x3498DB)
        embed.add_field(name="Сотрудник", value=f"<@{target_id}> (`{target_id}`)", inline=True)
        embed.add_field(name="Срок", value="14 дней истекли", inline=True)
        embed.add_field(name="Первоначальная причина", value=reason, inline=False)
        await channel.send(embed=embed)

    @classmethod
    async def log_guard_alert(
        cls,
        guild: discord.Guild,
        actor_id: int,
        action: str,
        strikes: int,
        details: str,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("🚨 Нарушение прав безопасности", color=CONFIG.danger_color)
        embed.add_field(name="Нарушитель", value=f"<@{actor_id}> (`{actor_id}`)", inline=True)
        embed.add_field(name="Действие", value=action, inline=True)
        embed.add_field(
            name="Замечания безопасности",
            value=f"`{strikes}/{CONFIG.max_security_strikes}`",
            inline=True,
        )
        embed.add_field(name="Детали", value=details, inline=False)
        embed.add_field(name="Статус отката", value="✅ Действие успешно заблокировано/откачено", inline=False)
        await channel.send(embed=embed)

    @classmethod
    async def log_quarantine(cls, guild: discord.Guild, member: discord.Member, strikes: int) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("⛔ Карантин и блокировка нарушителя", color=0x000000)
        embed.add_field(name="Пользователь", value=f"{member.mention} (`{member.id}`)", inline=True)
        embed.add_field(name="Причина", value=f"Достигнут лимит замечаний ({strikes}/{CONFIG.max_security_strikes})", inline=True)
        embed.add_field(
            name="Примененные санкции",
            value="Все роли аннулированы. Выдана изолирующая роль бана.",
            inline=False,
        )
        await channel.send(embed=embed)

    @classmethod
    async def log_blacklist_add(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        issuer_rank_title: str,
        reason: str,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("🚫 Внесение в ЧСКП", color=CONFIG.danger_color)
        embed.add_field(name="Пользователь", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Инициатор", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Должность инициатора", value=issuer_rank_title, inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Срок нахождения", value="Бессрочно (вечно)", inline=False)
        await channel.send(embed=embed)

    @classmethod
    async def log_blacklist_remove(
        cls,
        guild: discord.Guild,
        actor: discord.Member,
        target: discord.Member,
        reason: str,
    ) -> None:
        channel = guild.get_channel(CONFIG.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = cls._create_base_embed("🕊️ Вынесение из ЧСКП", color=CONFIG.success_color)
        embed.add_field(name="Пользователь", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Модератор", value=f"{actor.mention} (`{actor.id}`)", inline=True)
        embed.add_field(name="Причина вынесения", value=reason, inline=False)
        await channel.send(embed=embed)
