from enum import Enum, IntEnum


class BranchType(str, Enum):
    MODERATION = "Модерация"
    SUPPORT = "Саппорты"
    EVENTERS = "Эвентеры"
    STAFF = "Стафф"
    NONE = "Не состоит"


class PositionRank(IntEnum):
    NONE = 0
    RANK_1 = 1
    MASTER = 2
    CURATOR = 3
    DEPUTY_ADMIN = 4
    ADMIN = 5
    STAFF_ADMIN = 6
    OWNER = 7

    @property
    def display_name(self) -> str:
        names = {
            PositionRank.NONE: "Отсутствует",
            PositionRank.RANK_1: "Рядовой",
            PositionRank.MASTER: "Мастер",
            PositionRank.CURATOR: "Куратор",
            PositionRank.DEPUTY_ADMIN: "Зам.Администратора",
            PositionRank.ADMIN: "Администратор",
            PositionRank.STAFF_ADMIN: "Стафф Администратор",
            PositionRank.OWNER: "Владелец",
        }
        return names[self]


class GuardPermission(str, Enum):
    MANAGE_ROLES_PKM = "manage_roles_pkm"
    EDIT_ROLES = "edit_roles"
    CREATE_ROLES = "create_roles"
    DELETE_ROLES = "delete_roles"
    BAN_MEMBERS = "ban_members"
    KICK_MEMBERS = "kick_members"
    TIMEOUT_MEMBERS = "timeout_members"
    CREATE_CHANNELS = "create_channels"
    EDIT_CHANNELS = "edit_channels"
    DELETE_CHANNELS = "delete_channels"
    EDIT_SERVER = "edit_server"
    MANAGE_WEBHOOKS = "manage_webhooks"
    ADD_BOTS = "add_bots"

    @property
    def title_ru(self) -> str:
        labels = {
            GuardPermission.MANAGE_ROLES_PKM: "Выдача/снятие ролей (ПКМ)",
            GuardPermission.EDIT_ROLES: "Редактирование ролей",
            GuardPermission.CREATE_ROLES: "Создание ролей",
            GuardPermission.DELETE_ROLES: "Удаление ролей",
            GuardPermission.BAN_MEMBERS: "Бан участников",
            GuardPermission.KICK_MEMBERS: "Кик участников",
            GuardPermission.TIMEOUT_MEMBERS: "Таймаут (мут) участников",
            GuardPermission.CREATE_CHANNELS: "Создание каналов",
            GuardPermission.EDIT_CHANNELS: "Редактирование каналов",
            GuardPermission.DELETE_CHANNELS: "Удаление каналов/категорий",
            GuardPermission.EDIT_SERVER: "Настройки сервера",
            GuardPermission.MANAGE_WEBHOOKS: "Управление вебхуками",
            GuardPermission.ADD_BOTS: "Добавление ботов",
        }
        return labels[self]
