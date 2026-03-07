"""
bot_instance.py — Single shared Telegram bot instance.

Created once; imported by every module that needs to call the Telegram API.
Keeping the bot object here avoids circular imports between handler modules.
"""

import telebot
from bot_config import BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
