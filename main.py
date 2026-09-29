#!/usr/bin/env python3
"""
Kawaii World Discord Bot — Main Entrypoint for Hosting & Production.
Supports: Linux VPS (Ubuntu/Debian), Docker, Pterodactyl, Windows Server, Systemd, etc.
"""
import asyncio
import logging
import os
from pathlib import Path
import signal
import sys
import aiohttp
from dotenv import load_dotenv

# 1. Корневая директория проекта в sys.path для корректных импортов
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 2. Загрузка переменных окружения из .env в папке проекта
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# 3. Настройка кодировки UTF-8 для консоли
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 4. Настройка логирования (в консоль и файл bot.log)
log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

file_log_path = BASE_DIR / "bot.log"
try:
    file_handler = logging.FileHandler(file_log_path, encoding="utf-8", mode="a")
    file_handler.setFormatter(log_formatter)
    handlers = [console_handler, file_handler]
except Exception:
    handlers = [console_handler]

logging.basicConfig(
    level=logging.INFO,
    handlers=handlers,
)
logger = logging.getLogger("kawaii_entrypoint")

# Импорт бота после настройки окружения
from kawaii_core.bot import KawaiiBot
from kawaii_core.config import CONFIG


async def run_bot_lifecycle() -> None:
    token = (
        os.getenv("DISCORD_BOT_TOKEN")
        or os.getenv("DISCORD_TOKEN")
        or os.getenv("TOKEN")
        or CONFIG.bot_token
    )

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.critical(
            "❌ Токен бота не настроен! Укажите переменную окружения DISCORD_BOT_TOKEN или TOKEN в файле .env или в настройках хостинга."
        )
        sys.exit(1)

    retry_delay = 10
    bot: KawaiiBot | None = None
    stop_event = asyncio.Event()

    # Graceful shutdown для Linux/Docker/Pterodactyl/Systemd
    def handle_signal(sig_name: str) -> None:
        logger.info(f"Получен сигнал остановки ({sig_name}). Завершаем работу бота...")
        stop_event.set()
        if bot and not bot.is_closed():
            asyncio.create_task(bot.close())

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(s, lambda s=s: handle_signal(s.name))
            except NotImplementedError:
                pass

    while not stop_event.is_set():
        try:
            bot = KawaiiBot()
            async with bot:
                logger.info("Подключение к Discord Gateway...")
                await bot.start(token)
                break
        except (
            aiohttp.ClientConnectorError,
            aiohttp.ClientConnectorDNSError,
            aiohttp.ClientError,
            TimeoutError,
            OSError,
        ) as net_err:
            if stop_event.is_set():
                break
            logger.error(
                "\n"
                "========================================================================\n"
                "❌ [СЕТЕВАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К DISCORD]\n"
                f"Не удалось установить соединение: {net_err}\n"
                f"Повторная попытка через {retry_delay} секунд...\n"
                "========================================================================\n"
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=retry_delay)
            except asyncio.TimeoutError:
                pass
        except Exception as exc:
            if stop_event.is_set():
                break
            logger.critical("Неожиданная критическая ошибка: %s", exc, exc_info=True)
            break

    logger.info("Бот успешно остановлен.")


def main() -> None:
    try:
        asyncio.run(run_bot_lifecycle())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Работа бота завершена.")


if __name__ == "__main__":
    main()
