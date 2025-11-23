import logging
import asyncio

from concurrent.futures import ThreadPoolExecutor
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import RetryAfter
from time import sleep


class TelegramSender:
    def __init__(
        self,
        token,
        chat_id,
        alert_chat_id=0,
        bot_emoji="\U0001F916",  # 🤖
        top_emoji="\U0001F3C6",  # 🏆
        news_emoji="\U0001F4F0",  # 📰
    ):

        self.token = token
        self.chat_id = chat_id
        self.alert_chat_id = alert_chat_id

        self.bot_emoji = bot_emoji
        self.top_emoji = top_emoji
        self.news_emoji = news_emoji

        self.bot = Bot(self.token)

        self.logger = logging.getLogger("telegram-sender")

    def is_alert_chat_enabled(self):
        return self.alert_chat_id != 0 and self.alert_chat_id != self.chat_id

    async def send_message(self, message, is_alert_chat=False, reply_markup=None):
        chat_id = self.chat_id if not is_alert_chat else self.alert_chat_id

        self.logger.info(message)
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        except RetryAfter as e:
            self.logger.error(
                f"Flood limit is exceeded. Sleep {e.retry_after} seconds."
            )
            await asyncio.sleep(e.retry_after)
            # Resend message
            await self.send_message(message, is_alert_chat, reply_markup)
        except Exception as e:
            self.logger.error(str(e))

    async def send_generic_message(self, message, args=None, is_alert_chat=False, reply_markup=None):
        if args is not None:
            message = message.format(args)
        await self.send_message(self.bot_emoji + " " + message, is_alert_chat, reply_markup)

    async def send_report_message(self, message, args=None, is_alert_chat=False, reply_markup=None):
        if args is not None:
            message = message.format(args)
        await self.send_message(self.top_emoji + " " + message, is_alert_chat, reply_markup)

    async def send_news_message(self, message, args=None, is_alert_chat=False, reply_markup=None):
        if args is not None:
            message = message.format(args)
        await self.send_message(self.news_emoji + " " + message, is_alert_chat, reply_markup)
