import asyncio
import os
import threading
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_db, async_session, init_db
from models.Task import Task
from models.Post import Post
from models.User import User
import aiogram
from aiogram import Bot
import configparser
import logging
from avito_parser import AvitoParser
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=BOT_TOKEN)

class ParserWorker:
    def __init__(self, task: Task, session: AsyncSession):
        self.task = task
        self.session = session
        self.user = None

    async def init(self):
        """Инициализация воркера"""
        try:
            result = await self.session.execute(
                select(User).where(User.id == self.task.app_user_id)
            )
            self.user = result.scalar_one()
            if not self.user:
                raise ValueError(f"Пользователь с ID {self.task.app_user_id} не найден")
        except Exception as e:
            logger.error(f"Ошибка при инициализации воркера: {str(e)}", exc_info=True)
            raise

    async def process_task(self):
        try:
            await self.init()
            logger.info(f"Начинаем обработку задачи {self.task.id} для URL: {self.task.url}")
            
            # Создаем парсер
            parser = AvitoParser(self.task, self.session)
            
            # Получаем новые посты
            new_posts = await parser.parse()
            
            if new_posts:
                logger.info(f"Найдено {len(new_posts)} новых объявлений для задачи {self.task.id}")
                for post in new_posts:
                    message = f"🏠 {post['name']}\n"
                    message += f"💰 Цена: {post['price']}\n\n"
                    message += f"🔗 {post['url']}\n"
                    await bot.send_message(
                        chat_id=self.user.chat_id,
                        text=message,
                        parse_mode='HTML'
                    )
            else:
                logger.info(f"Новых объявлений не найдено для задачи {self.task.id}")

            # Обновляем время следующего запуска
            current_time = datetime.now()
            self.task.next_run_at = current_time.replace(microsecond=0) + timedelta(minutes=self.task.interval)
            self.task.last_run_at = current_time.replace(microsecond=0)
            logger.info(f"Обновляем время следующего запуска для задачи {self.task.id}: {self.task.next_run_at}")
            
            # Сохраняем изменения в задаче
            await self.session.commit()
            logger.info(f"Задача {self.task.id} успешно обработана. Следующий запуск в {self.task.next_run_at}")

        except Exception as e:
            logger.error(f"Ошибка при обработке задачи {self.task.id}: {str(e)}", exc_info=True)
            await self.session.rollback()
            raise

class TaskScheduler:
    def __init__(self):
        self.running_tasks = set()

    async def get_tasks_to_run(self, session: AsyncSession) -> list[Task]:
        """Получение списка задач, которые нужно запустить"""
        try:
            current_time = datetime.now()
            result = await session.execute(
                select(Task).where(
                    Task.next_run_at <= current_time, #Если время следующего запуска меньше или равно текущему времени  
                    Task.end_date >= current_time, #Если время окончания задачи больше или равно текущему времени
                    Task.is_active == True #Если задача активна
                )
            )
            tasks = result.scalars().all()
            logger.info(f"Найдено {len(tasks)} задач для выполнения")
            return tasks
        except Exception as e:
            logger.error(f"Ошибка при получении списка задач: {str(e)}", exc_info=True)
            raise

    async def run_task(self, task: Task):
        """Запуск задачи в отдельном потоке"""
        if task.id in self.running_tasks:
            logger.warning(f"Задача {task.id} уже выполняется")
            return

        self.running_tasks.add(task.id)
        try:
            # Создаем отдельную сессию для парсера
            async with async_session() as parser_session:
                parser = AvitoParser(task, parser_session)
                new_posts = await parser.parse()

            # Создаем отдельную сессию для обновления задачи
            async with async_session() as task_session:
                try:
                    # Получаем актуальную версию задачи
                    result = await task_session.execute(
                        select(Task).where(Task.id == task.id)
                    )
                    current_task = result.scalar_one()
                    
                    # Обновляем время следующего запуска
                    current_time = datetime.now().replace(microsecond=0)
                    current_task.next_run_at = current_time + timedelta(minutes=current_task.interval)
                    current_task.last_run_at = current_time
                    
                    logger.info(f"Обновляем время для задачи {current_task.id}:")
                    logger.info(f"Текущее время: {current_time}")
                    logger.info(f"Следующий запуск: {current_task.next_run_at}")
                    logger.info(f"Последний запуск: {current_task.last_run_at}")
                    
                    # Сохраняем изменения в задаче
                    await task_session.commit()
                    logger.info(f"Задача {current_task.id} успешно обновлена")

                    # Отправляем сообщения о новых постах
                    if new_posts:
                        user = None
                        async with async_session() as user_session:
                            try:
                                result = await user_session.execute(
                                    select(User).where(User.id == current_task.app_user_id)
                                )
                                user = result.scalar_one()
                                if user:
                                    logger.info(f"Отправляем {10 if len(new_posts) >= 10 else len(new_posts) } сообщений пользователю {user.id}")
                                    for number, post in enumerate(new_posts):
                                        
                                        if number >= 10: 
                                            break

                                        message = f"🏠 {post['name']}\n"
                                        message += f"💰 Цена: {post['price']}\n\n"
                                        message += f"🔗 {post['url']}\n"
                                        await bot.send_message(
                                            chat_id=user.chat_id,
                                            text=message,
                                            parse_mode='HTML'
                                        )
                                    logger.info(f"Сообщения успешно отправлены пользователю {user.id}")
                            except Exception as e:
                                logger.error(f"Ошибка при отправке сообщений: {str(e)}", exc_info=True)
                                await user_session.rollback()
                                raise
                except Exception as e:
                    logger.error(f"Ошибка при обновлении задачи {task.id}: {str(e)}", exc_info=True)
                    await task_session.rollback()
                    raise

        except Exception as e:
            logger.error(f"Ошибка при выполнении задачи {task.id}: {str(e)}", exc_info=True)
            raise
        finally:
            self.running_tasks.remove(task.id)

    async def process_tasks(self):
        """Обработка всех задач"""
        try:
            async with async_session() as session:
                tasks = await self.get_tasks_to_run(session)
                if tasks:
                    logger.info(f"Запускаем {len(tasks)} задач")
                    await asyncio.gather(*[self.run_task(task) for task in tasks])
        except Exception as e:
            logger.error(f"Ошибка при обработке задач: {str(e)}", exc_info=True)

    async def run(self):
        """Основной цикл планировщика"""
        logger.info("Запуск планировщика задач")
        while True:
            try:
                await self.process_tasks()
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {str(e)}", exc_info=True)
            
            # Ждем 1 минуту перед следующей проверкой
            await asyncio.sleep(60)

async def main():
    try:
        # Инициализируем базу данных
        await init_db()
        
        # Запускаем планировщик
        scheduler = TaskScheduler()
        await scheduler.run()
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {str(e)}", exc_info=True)
        exit(1) 