import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from datetime import datetime
import logging
from typing import List, Dict
import asyncio
from models.Post import Post
from models.Task import Task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import time
import re

logger = logging.getLogger(__name__)

class AvitoParser:
    def __init__(self, task: Task, session: AsyncSession):
        self.task = task
        self.session = session
        self.driver = None
        self.data = []

    async def setup_driver(self):
        """Инициализация драйвера Chrome"""
        self.driver = uc.Chrome()

    async def get_existing_posts(self) -> List[str]:
        """Получение списка существующих post_id для задачи"""
        result = await self.session.execute(
            select(Post.post_id).where(Post.task_id == self.task.id)
        )
        return [row[0] for row in result.all()]

    async def parse_page(self) -> List[Dict]:
        """Парсинг страницы Авито"""
        try:
            self.driver.get(self.task.url)
            time.sleep(2)  # Даем странице загрузиться

            items = []
            sale_ads = self.driver.find_elements(By.CSS_SELECTOR, "[data-marker='item']")
            
            for ad in sale_ads:
                try:
                    name = ad.find_element(By.CSS_SELECTOR, "[itemprop='name']").text
                    url = ad.find_element(By.CSS_SELECTOR, "[data-marker='item-title']").get_attribute("href")
                    price = ad.find_element(By.CSS_SELECTOR, "[itemprop='price']").get_attribute("content")
                    published_time = ad.find_element(By.CSS_SELECTOR, "[data-marker='item-date']").text
                    base_url = url.split('?')[0]
                    post_id = re.search(r'(\d+)$', base_url).group(1)
                    print(post_id)

                    items.append({
                        'name': name,
                        'url': base_url,
                        'price': price,
                        'published_time': published_time,
                        'post_id': post_id
                    })
                except Exception as e:
                    logger.error(f"Ошибка при парсинге объявления: {str(e)}")
                    continue

            return items

        except Exception as e:
            logger.error(f"Ошибка при парсинге страницы: {str(e)}")
            return []

    async def save_new_posts(self, new_posts: List[Dict]):
        """Сохранение новых постов в базу данных"""
        try:
            for post_data in new_posts:
                post = Post(
                    task_id=self.task.id,
                    post_id=post_data['post_id'],
                    title=post_data['name'],
                    url=post_data['url'],
                    price=post_data['price'],
                    created_at=datetime.now().replace(microsecond=0)  # Убираем микросекунды
                )
                self.session.add(post)
                logger.info(f"Добавлен новый пост: {post.post_id} для задачи {self.task.id}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении постов: {str(e)}", exc_info=True)
            raise

    async def parse(self) -> List[Dict]:
        """Основной метод парсинга"""
        try:
            await self.setup_driver()
            existing_posts = await self.get_existing_posts()
            logger.info(f"Получено {len(existing_posts)} существующих постов для задачи {self.task.id}")
            
            all_posts = await self.parse_page()
            logger.info(f"Получено {len(all_posts)} постов с Авито для задачи {self.task.id}")
            
            # Фильтруем только новые посты
            new_posts = [post for post in all_posts if post['post_id'] not in existing_posts]
            logger.info(f"Найдено {len(new_posts)} новых постов для задачи {self.task.id}")
            
            if new_posts:
                await self.save_new_posts(new_posts)
                await self.session.commit()
                logger.info(f"Успешно сохранено {len(new_posts)} новых постов для задачи {self.task.id}")
            
            return new_posts

        except Exception as e:
            logger.error(f"Ошибка в процессе парсинга: {str(e)}", exc_info=True)
            await self.session.rollback()
            return []
        
        finally:
            if self.driver:
                self.driver.quit() 