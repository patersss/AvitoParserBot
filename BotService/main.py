import asyncio
import logging
import configparser
from datetime import datetime, timedelta
from typing import Dict
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session
from models.User import User
from models.Task import Task
from models.Post import Post
# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
try:
    BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
    logger.info("Конфигурация успешно загружена")
except Exception as e:
    logger.error(f"Ошибка при загрузке конфигурации: {str(e)}")
    raise

# Инициализация бота и диспетчера
try:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    logger.info("Бот и диспетчер успешно инициализированы")
except Exception as e:
    logger.error(f"Ошибка при инициализации бота: {str(e)}")
    raise

# Словарь для хранения временных данных пользователей
user_states: Dict[int, Dict] = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    chat_id = message.chat.id
    logger.info(f"Получена команда /start от чата {chat_id}")
    
    try:
        # Проверяем существование пользователя в БД
        async with async_session() as session:
            # Ищем пользователя по chat_id
            query = select(User).where(User.chat_id == chat_id)
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.info(f"Создание нового пользователя с chat_id {chat_id}")
                user = User(
                    name=message.from_user.username,
                    chat_id=chat_id
                )
                session.add(user)
                await session.commit()
            elif user.name != message.from_user.username:
                # Обновляем имя пользователя если оно изменилось
                logger.info(f"Обновление имени пользователя для chat_id {chat_id}")
                user.name = message.from_user.username
                await session.commit()
        
        await message.answer(
            "Привет! Я бот для отслеживания объявлений на Авито.\n"
            "Отправь мне ссылку на поиск Авито, и я буду отслеживать новые объявления.\n"
            "Используй /help для получения справки."
        )
        logger.info(f"Приветственное сообщение отправлено в чат {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start: {str(e)}")
        await message.answer("Произошла ошибка при обработке команды. Пожалуйста, попробуйте позже.")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    chat_id = message.chat.id
    help_text = (
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/add - Добавить новую задачу для отслеживания\n"
        "/list - Показать список отслеживаемых задач\n"
        "/remove - Удалить задачу из отслеживания\n\n"
        "При добавлении задачи укажите:\n"
        "1. Название задачи (от 3 до 50 символов)\n"
        "2. Ссылку на поиск Авито\n"
        "3. Количество дней для отслеживания\n"
        "4. Интервал проверки в минутах (минимум 10 минут)\n\n"
        "Управление задачами:\n"
        "• В списке задач (/list) вы можете:\n"
        "  - Изменить название задачи\n"
        "  - Изменить интервал проверки\n"
        "• Используйте /remove для удаления задачи"
    )
    await message.answer(help_text)
    logger.info(f"Справка отправлена в чат {chat_id}")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    """Обработчик команды /list"""
    chat_id = message.chat.id
    logger.info(f"Получена команда /list от чата {chat_id}")
    
    async with async_session() as session:
        query_for_user = select(User).where(User.chat_id == chat_id)
        result_for_user = await session.execute(query_for_user)
        user_id = result_for_user.scalar_one().id

        query = select(Task).where(Task.app_user_id == user_id, Task.is_active == True)
        result = await session.execute(query)
        tasks = result.scalars().all()
        
        if not tasks:
            await message.answer("У вас нет активных задач отслеживания.")
            return
        
        await message.answer("Ваши активные задачи:")
        for task in tasks:
            response = (
                f"📝 Название: {task.task_name}\n"
                f"🔗 Ссылка: {task.url}\n"
                f"📅 Дата окончания отслеживания: {task.end_date}\n"
                f"⏱ Интервал проверки: {task.interval} минут\n"
                f"📊 ID задачи: {task.id}\n\n"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{task.id}"),
                    InlineKeyboardButton(text="⏱ Изменить интервал", callback_data=f"edit_interval_{task.id}")
                ]
            ])
            await message.answer(response, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith('edit_name_'))
async def process_edit_name(callback_query: types.CallbackQuery):
    """Обработка запроса на изменение названия задачи"""
    chat_id = callback_query.message.chat.id
    task_id = int(callback_query.data.split('_')[-1])
    
    user_states[chat_id] = {
        "state": "waiting_new_name",
        "task_id": task_id
    }
    
    await callback_query.message.answer(
        "Введите новое название для задачи (от 3 до 50 символов):"
    )
    await callback_query.answer()

@dp.message(lambda message: message.chat.id in user_states and user_states[message.chat.id]["state"] == "waiting_new_name")
async def process_new_name(message: types.Message):
    """Обработка нового названия задачи"""
    chat_id = message.chat.id
    task_id = user_states[chat_id]["task_id"]
    new_name = message.text.strip()
    
    if len(new_name) < 3 or len(new_name) > 50:
        await message.answer("Название задачи должно быть от 3 до 50 символов.")
        return
    
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if task:
            old_name = task.task_name
            task.task_name = new_name
            await session.commit()
            await message.answer(f"Название задачи изменено с '{old_name}' на '{new_name}'")
            logger.info(f"Изменено название задачи {task_id} в чате {chat_id}")
        else:
            await message.answer("Задача не найдена или у вас нет прав на её редактирование.")
    
    del user_states[chat_id]

@dp.callback_query(lambda c: c.data.startswith('edit_interval_'))
async def process_edit_interval(callback_query: types.CallbackQuery):
    """Обработка запроса на изменение интервала проверки"""
    chat_id = callback_query.message.chat.id
    task_id = int(callback_query.data.split('_')[-1])
    
    user_states[chat_id] = {
        "state": "waiting_new_interval",
        "task_id": task_id
    }
    
    await callback_query.message.answer(
        "Введите новый интервал проверки в минутах (минимум 10 минут):"
    )
    await callback_query.answer()

@dp.message(lambda message: message.chat.id in user_states and user_states[message.chat.id]["state"] == "waiting_new_interval")
async def process_new_interval(message: types.Message):
    """Обработка нового интервала проверки"""
    chat_id = message.chat.id
    task_id = user_states[chat_id]["task_id"]
    
    try:
        new_interval = int(message.text)
        if new_interval < 10:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите число не менее 10 минут.")
        return
    
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if task:
            old_interval = task.interval
            task.interval = new_interval
            await session.commit()
            await message.answer(
                f"Интервал проверки для задачи '{task.task_name}' изменен с {old_interval} на {new_interval} минут"
            )
            logger.info(f"Изменен интервал задачи {task_id} в чате {chat_id}")
        else:
            await message.answer("Задача не найдена или у вас нет прав на её редактирование.")
    
    del user_states[chat_id]

@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    """Обработчик команды /remove"""
    chat_id = message.chat.id
    logger.info(f"Получена команда /remove от чата {chat_id}")
    
    async with async_session() as session:
        query_for_user = select(User).where(User.chat_id == chat_id)
        result_for_user = await session.execute(query_for_user)
        user_id = result_for_user.scalar_one().id

        query = select(Task).where(Task.app_user_id == user_id, Task.is_active == True)
        result = await session.execute(query)
        tasks = result.scalars().all()
        
        if not tasks:
            await message.answer("У вас нет активных задач для удаления.")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Удалить: {task.task_name}", callback_data=f"remove_{task.id}")]
            for task in tasks
        ])
        
        await message.answer("Выберите задачу для удаления:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith('remove_'))
async def process_remove(callback_query: types.CallbackQuery):
    """Обработка удаления задачи"""
    chat_id = callback_query.message.chat.id
    task_id = int(callback_query.data.split('_')[-1])
    logger.info(f"Получен запрос на удаление задачи {task_id} из чата {chat_id}")
    
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if task:
            task_name = task.task_name
            task.is_active = False
            await session.commit()
            await callback_query.message.answer(f"Задача '{task_name}' успешно удалена.")
            logger.info(f"Задача {task_id} удалена из чата {chat_id}")
        else:
            await callback_query.message.answer("Задача не найдена или у вас нет прав на её удаление.")
            logger.warning(f"Попытка удалить несуществующую задачу {task_id} из чата {chat_id}")
    
    await callback_query.answer()

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    """Обработчик команды /add"""
    chat_id = message.chat.id
    logger.info(f"Получена команда /add от чата {chat_id}")
    
    # Проверяем количество активных задач
    async with async_session() as session:
        query_for_user = select(User).where(User.chat_id == chat_id)
        result_for_user = await session.execute(query_for_user)
        user_id = result_for_user.scalar_one().id
        query = select(Task).where(Task.app_user_id == user_id, Task.is_active == True)
        result = await session.execute(query)
        active_tasks = result.scalars().all()
        
        if len(active_tasks) >= 5:
            await message.answer("У вас уже максимальное количество отслеживаемых задач (5).")
            return
    
    user_states[chat_id] = {"state": "waiting_name"}
    await message.answer("Пожалуйста, введите название для задачи:")

@dp.message(lambda message: message.chat.id in user_states and user_states[message.chat.id]["state"] == "waiting_name")
async def process_name(message: types.Message):
    """Обработка названия задачи"""
    chat_id = message.chat.id
    task_name = message.text.strip()
    
    if len(task_name) < 3 or len(task_name) > 50:
        await message.answer("Название задачи должно быть от 3 до 50 символов.")
        return
    
    user_states[chat_id].update({
        "task_name": task_name,
        "state": "waiting_url"
    })
    await message.answer("Пожалуйста, отправьте ссылку на поиск Авито.")

@dp.message(lambda message: message.chat.id in user_states and user_states[message.chat.id]["state"] == "waiting_url")
async def process_url(message: types.Message):
    """Обработка URL от пользователя"""
    chat_id = message.chat.id
    url = message.text
    
    if not url.startswith("https://www.avito.ru/"):
        await message.answer("Пожалуйста, отправьте корректную ссылку на Авито.")
        return
    
    user_states[chat_id].update({
        "url": url,
        "state": "waiting_days"
    })
    await message.answer("Укажите количество дней для отслеживания (1-30):")

@dp.message(lambda message: message.chat.id in user_states and user_states[message.chat.id]["state"] == "waiting_days")
async def process_days(message: types.Message):
    """Обработка количества дней"""
    chat_id = message.chat.id
    
    try:
        days = int(message.text)
        if not 1 <= days <= 30:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите число от 1 до 30.")
        return
    
    user_states[chat_id].update({
        "days": days,
        "state": "waiting_interval"
    })
    await message.answer("Укажите интервал проверки в минутах (минимум 10):")

@dp.message(lambda message: message.chat.id in user_states and user_states[message.chat.id]["state"] == "waiting_interval")
async def process_interval(message: types.Message):
    """Обработка интервала проверки"""
    chat_id = message.chat.id
    
    try:
        interval = int(message.text)
        if interval < 10:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите число не менее 10 минут.")
        return
    
    # Сохраняем задачу в базу данных
    async with async_session() as session:
        result = await session.execute(select(User).where(User.chat_id == chat_id))
        user_id = result.scalar_one().id
        task = Task(
            app_user_id=user_id,
            task_name=user_states[chat_id]["task_name"],
            url=user_states[chat_id]["url"],
            end_date=datetime.now() + timedelta(days=user_states[chat_id]["days"]),
            interval=interval,
            is_active=True,
            next_run_at=datetime.now() - timedelta(minutes=2)
        )
        session.add(task)
        await session.commit()
        logger.info(f"Создана новая задача для чата {chat_id}")
    
    await message.answer(
        "Задача успешно добавлена!\n"
        f"📝 Название: {user_states[chat_id]['task_name']}\n"
        f"🔗 Ссылка: {user_states[chat_id]['url']}\n"
        f"📅 Дата окончания отслеживания: {datetime.now() + timedelta(days=user_states[chat_id]['days'])}\n"
        f"⏱ Проверка осуществляется каждые {interval} минут\n"
        "В ближайшее время вы получите ссылки на последние объявления."
    )
    
    # Очищаем состояние пользователя
    del user_states[chat_id]

async def set_commands(bot: Bot):
    """Установка команд бота"""
    commands = [
        BotCommand(
            command="start",
            description="Начать работу с ботом"
        ),
        BotCommand(
            command="help",
            description="Показать справку"
        ),
        BotCommand(
            command="add",
            description="Добавить новую задачу для отслеживания"
        ),
        BotCommand(
            command="list",
            description="Показать список отслеживаемых задач"
        ),
        BotCommand(
            command="remove",
            description="Удалить задачу из отслеживания"
        )
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def main():
    """Основная функция запуска бота"""
    try:
        logger.info("Запуск бота...")
        # Устанавливаем команды бота
        await set_commands(bot)
        logger.info("Команды бота установлены")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        raise
