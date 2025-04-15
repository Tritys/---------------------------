import asyncio
import logging
import random
import aiohttp
import json
import sys
import io
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook
from aiogram import types
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from datetime import datetime
from mistralai import Mistral
from typing import Optional
from collections import deque

# Фикс кодировки для Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Настройки API
API_KEY = ""
MODEL = "mistral-small-latest"
IMAGE_API_KEY = ""
BOT_TOKEN = ""
ADMIN_ID = 
CHANNEL_ID =   # Убедитесь, что ID правильный

# Инициализация бота с увеличенными таймаутами
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = Mistral(api_key=API_KEY) if API_KEY else None

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_CAPTION_LENGTH = 1024

# Очередь постов
post_queue = deque()

# Знаки зодиака
ZODIAC_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", 
    "Лев", "Дева", "Весы", "Скорпион",
    "Стрелец", "Козерог", "Водолей", "Рыбы"
]

# Темы для постов
MYSTIC_TOPICS = [
    "Таро и их скрытые значения",
    "Руны: древний язык символов",
    "Нумерология в повседневной жизни",
    "Лунные циклы и их влияние",
    "Энергетика камней и кристаллов"
]

ASTROLOGY_FACTS = [
    "История астрологии: от древности до наших дней",
    "Как планеты влияют на характер человека",
    "Интересные совпадения в астрологии",
    "Самые сильные комбинации знаков зодиака",
    "Как астрология используется в современной психологии"
]

# Индекс текущего знака
current_zodiac_index = datetime.now().day % len(ZODIAC_SIGNS)

async def check_internet() -> bool:
    """Проверка интернет-соединения"""
    for _ in range(3):  # 3 попытки
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get("http://www.google.com"):
                    return True
        except:
            await asyncio.sleep(2)
    return False

async def notify_admin(text: str):
    """Отправка уведомления администратору"""
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logger.error(f"Ошибка уведомления администратора: {e}")

async def generate_image(prompt: str) -> Optional[str]:
    """Генерация изображения через API"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(
                "https://neuroimg.art/api/v1/free-generate",
                json={"token": IMAGE_API_KEY, "prompt": prompt}
            ) as resp:
                async for line in resp.content:
                    if b'"status":"SUCCESS"' in line:
                        return line.decode().split('"image_url":"')[1].split('"')[0]
    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {e}")
    return None

async def download_image(url: str) -> Optional[bytes]:
    """Загрузка изображения по URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
    return None

async def send_post(text: str, post_type: str):
    """Отправка поста в канал"""
    if not text:
        logger.error("Пустой текст поста")
        return

    for attempt in range(MAX_RETRIES):
        try:
            # Проверка доступа к каналу
            try:
                chat = await bot.get_chat(CHANNEL_ID)
                logger.info(f"Публикация в канал: {chat.title}")
            except Exception as e:
                logger.error(f"Ошибка доступа к каналу: {e}")
                await notify_admin(f"❌ Ошибка доступа к каналу: {e}")
                return

            # Пытаемся сгенерировать и отправить изображение
            image_sent = False
            try:
                image_url = await generate_image(f"{post_type}: {text[:50]}")
                if image_url:
                    image_data = await download_image(image_url)
                    if image_data:
                        await bot.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=BufferedInputFile(image_data, "image.jpg"),
                            caption=text[:MAX_CAPTION_LENGTH],
                            parse_mode="Markdown"
                        )
                        image_sent = True
            except Exception as e:
                logger.warning(f"Не удалось сгенерировать/отправить изображение: {e}")

            # Если изображение не отправилось, отправляем только текст
            if not image_sent:
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
                    parse_mode="Markdown"
                )
            return  # Успешная отправка
            
        except Exception as e:
            logger.error(f"Ошибка отправки поста (попытка {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    
    # Если все попытки неудачны
    post_queue.append((text, post_type))
    await notify_admin(f"⚠ Не удалось отправить пост после {MAX_RETRIES} попыток")
    
    # Если все попытки неудачны
    post_queue.append((text, post_type))
    await notify_admin(f"⚠ Не удалось отправить пост после {MAX_RETRIES} попыток")

async def generate_content(prompt: str, max_tokens=500) -> str:
    """Генерация текста через Mistral API"""
    try:
        response = client.chat.complete(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка генерации контента: {e}")
        return ""

async def generate_mini_horoscope() -> str:
    """Генерация мини-гороскопа"""
    day = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"][datetime.now().weekday()]
    prompt = f"Создай краткий гороскоп на {day} для всех знаков. Формат: [Знак] [Эмодзи]: [Совет 3-5 слов]. Начни с приветствия."
    content = await generate_content(prompt)
    return f"🌅 ДОБРОЕ УТРО! 🌅\n\n{content}"

async def generate_daily_horoscope() -> str:
    """Генерация ежедневного гороскопа"""
    global current_zodiac_index
    zodiac = ZODIAC_SIGNS[current_zodiac_index]
    current_zodiac_index = (current_zodiac_index + 1) % len(ZODIAC_SIGNS)
    prompt = f"Напиши гороскоп для {zodiac} на сегодня (3-5 предложений). Тон: позитивный."
    content = await generate_content(prompt)
    return f"🔮 {zodiac.upper()} 🔮\n\n{content}"

async def generate_fact() -> str:
    """Генерация астрологического факта"""
    prompt = "Расскажи интересный астрологический факт (3-5 предложений). Добавь эмодзи."
    content = await generate_content(prompt)
    return f"🌌 АСТРОЛОГИЧЕСКИЙ ФАКТ 🌌\n\n{content}"

async def generate_night_wish() -> str:
    """Генерация вечернего пожелания"""
    prompt = "Напиши доброе пожелание на ночь (2-3 предложения) с астрологическим советом."
    content = await generate_content(prompt, 200)
    return f"🌙 СПОКОЙНОЙ НОЧИ! 🌙\n\n{content}"


try:
    with open('zodiac_index.txt', 'r') as f:
        current_zodiac_index = int(f.read().strip())
except (FileNotFoundError, ValueError):
    current_zodiac_index = datetime.now().day % len(ZODIAC_SIGNS)

def save_zodiac_index():
    """Сохраняет текущий индекс знака зодиака в файл"""
    with open('zodiac_index.txt', 'w') as f:
        f.write(str(current_zodiac_index))

async def generate_daily_horoscope() -> str:
    """Генерация ежедневного гороскопа"""
    global current_zodiac_index
    zodiac = ZODIAC_SIGNS[current_zodiac_index]
    current_zodiac_index = (current_zodiac_index + 1) % len(ZODIAC_SIGNS)
    save_zodiac_index()  # Сохраняем новый индекс
    
    prompt = f"Напиши гороскоп для {zodiac} на сегодня (3-5 предложений). Тон: позитивный."
    content = await generate_content(prompt)
    return f"🔮 {zodiac.upper()} 🔮\n\n{content}"

async def posting_loop():
    """Основной цикл публикации постов"""
    while True:
        try:
            if not await check_internet():
                logger.warning("Нет интернет-соединения")
                await asyncio.sleep(60)
                continue

            now = datetime.now()
            today = now.date()
            hour = now.hour
            minute = now.minute

            # Утренний мини-гороскоп (8:00)
            if hour == 8 and minute < 30:
                if text := await generate_mini_horoscope():
                    await send_post(text, "horoscope")
                    await asyncio.sleep(3600)  # Ждем час перед следующей проверкой
                    continue

            # Вечерний пост (20:00)
            if hour == 20 and minute < 30:
                if text := await generate_night_wish():
                    await send_post(text, "mystic")
                    await asyncio.sleep(3600)
                    continue

            # Гороскоп для знака зодиака (1 раз в день в 12:00)
            if hour == 12 and minute < 30:
                if text := await generate_daily_horoscope():
                    await send_post(text, "horoscope")
                    await asyncio.sleep(3600)
                    continue

            # Факты (каждые 6 часов)
            if hour % 6 == 0 and minute < 30:
                if text := await generate_fact():
                    await send_post(text, "fact")
                    await asyncio.sleep(3600)
                    continue
            
            await asyncio.sleep(300)  # Проверка каждые 5 минут
            
        except Exception as e:
            logger.error(f"Ошибка в цикле публикаций: {e}")
            await asyncio.sleep(60)

async def health_check():
    """Проверка состояния бота"""
    while True:
        try:
            if not await check_internet():
                await notify_admin("⚠ Нет интернет-соединения")
            
            # Проверка доступности API
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.mistral.ai/health", timeout=10):
                        pass
            except Exception as e:
                await notify_admin(f"⚠ Проблемы с Mistral API: {str(e)}")
            
            await asyncio.sleep(3600)  # Проверка каждый час
        except Exception as e:
            logger.error(f"Ошибка health check: {e}")
            await asyncio.sleep(300)

async def process_queue():
    """Обработка очереди постов"""
    while True:
        if post_queue:
            text, post_type = post_queue.popleft()
            await send_post(text, post_type)
        await asyncio.sleep(10)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer("🔮 Бот астрологических предсказаний запущен!")

async def on_startup():
    """Действия при запуске бота"""
    await bot(DeleteWebhook(drop_pending_updates=True))
    await notify_admin("✅ Бот успешно запущен")
    asyncio.create_task(posting_loop())
    asyncio.create_task(process_queue())
    asyncio.create_task(health_check())  # Добавляем health check

async def main():
    """Основная функция"""
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")