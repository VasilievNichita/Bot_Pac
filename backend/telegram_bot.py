#!/usr/bin/env python3
"""
Telegram Quiz Bot - PCB Design Quiz
Created based on PowerPoint presentations about PCB (Printed Circuit Board) technology
"""

import os
import json
import random
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]

# Telegram Bot Token
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Load questions from JSON file
QUESTIONS_FILE = ROOT_DIR / 'questions.json'

def load_questions():
    """Load questions from JSON file"""
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['questions']

QUESTIONS = load_questions()


async def get_user_stats(user_id: int) -> dict:
    """Get user statistics from MongoDB"""
    stats = await db.quiz_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        stats = {
            "user_id": user_id,
            "total_answered": 0,
            "correct_answers": 0,
            "wrong_answers": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat()
        }
        await db.quiz_stats.insert_one(stats)
    return stats


async def update_user_stats(user_id: int, is_correct: bool):
    """Update user statistics after answering"""
    update_data = {
        "$inc": {
            "total_answered": 1,
            "correct_answers": 1 if is_correct else 0,
            "wrong_answers": 0 if is_correct else 1
        },
        "$set": {
            "last_activity": datetime.now(timezone.utc).isoformat()
        }
    }
    await db.quiz_stats.update_one(
        {"user_id": user_id},
        update_data,
        upsert=True
    )


async def get_random_question(user_id: int) -> dict:
    """Get a random question for the user"""
    question = random.choice(QUESTIONS)
    
    # Store current question for user
    await db.current_questions.update_one(
        {"user_id": user_id},
        {"$set": {
            "question_id": question['id'],
            "correct_answer": question['correct'],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return question


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Initialize user stats if not exists
    await get_user_stats(user_id)
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🎓 Добро пожаловать в Quiz Bot по проектированию печатных плат (PCB)!\n\n"
        "📚 Этот бот содержит 180 вопросов по темам:\n"
        "• История печатных плат\n"
        "• Типы и классификация ПП\n"
        "• Материалы и технологии производства\n"
        "• Проектирование и расчёт параметров\n"
        "• Проверка и контроль качества\n\n"
        "🎯 Нажмите кнопку ниже, чтобы начать тест!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 Начать тест", callback_data="start_quiz")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="show_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def show_question(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE, message_id: int = None):
    """Show a random question to the user"""
    question = await get_random_question(user_id)
    
    # Format question text
    question_text = (
        f"❓ *Вопрос {question['id']} из 180*\n"
        f"📌 Тема: _{question['topic']}_\n\n"
        f"{question['question']}\n\n"
    )
    
    # Create answer buttons
    keyboard = []
    options = question['options']
    for key in ['a', 'b', 'c', 'd']:
        if key in options:
            keyboard.append([
                InlineKeyboardButton(
                    f"{key.upper()}) {options[key]}", 
                    callback_data=f"answer_{key}"
                )
            ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=question_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=question_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_answer: str):
    """Handle user's answer"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Get current question
    current_q = await db.current_questions.find_one({"user_id": user_id}, {"_id": 0})
    
    if not current_q:
        await query.answer("❌ Ошибка: вопрос не найден. Начните заново.")
        return
    
    correct_answer = current_q['correct_answer']
    question_id = current_q['question_id']
    
    # Find the question to get options
    question = next((q for q in QUESTIONS if q['id'] == question_id), None)
    
    if not question:
        await query.answer("❌ Ошибка: вопрос не найден.")
        return
    
    is_correct = selected_answer == correct_answer
    
    # Update statistics
    await update_user_stats(user_id, is_correct)
    
    # Get updated stats
    stats = await get_user_stats(user_id)
    
    # Prepare result message
    if is_correct:
        result_emoji = "✅"
        result_text = "Правильно!"
    else:
        result_emoji = "❌"
        result_text = "Неправильно!"
    
    correct_option_text = question['options'][correct_answer]
    
    message_text = (
        f"{result_emoji} *{result_text}*\n\n"
        f"📝 Ваш ответ: *{selected_answer.upper()}*\n"
        f"✅ Правильный ответ: *{correct_answer.upper()})* {correct_option_text}\n\n"
        f"📊 Текущий счёт: {stats['correct_answers']}/{stats['total_answered']} "
        f"({round(stats['correct_answers']/stats['total_answered']*100 if stats['total_answered'] > 0 else 0, 1)}%)"
    )
    
    # Create navigation buttons
    keyboard = [
        [InlineKeyboardButton("➡️ Следующий вопрос", callback_data="next_question")],
        [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    await query.answer()


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    query = update.callback_query
    user_id = query.from_user.id
    
    stats = await get_user_stats(user_id)
    
    total = stats['total_answered']
    correct = stats['correct_answers']
    wrong = stats['wrong_answers']
    
    if total > 0:
        percentage = round(correct / total * 100, 1)
    else:
        percentage = 0
    
    # Determine skill level
    if percentage >= 90:
        level = "🏆 Эксперт"
    elif percentage >= 70:
        level = "🥇 Продвинутый"
    elif percentage >= 50:
        level = "🥈 Средний"
    elif percentage >= 30:
        level = "🥉 Начинающий"
    else:
        level = "📚 Ученик"
    
    stats_text = (
        f"📊 *Ваша статистика*\n\n"
        f"📝 Всего ответов: *{total}*\n"
        f"✅ Правильных: *{correct}*\n"
        f"❌ Неправильных: *{wrong}*\n\n"
        f"📈 Процент правильных: *{percentage}%*\n"
        f"🎯 Уровень: *{level}*\n\n"
        f"💡 В базе 180 вопросов по печатным платам.\n"
        f"Продолжайте отвечать для улучшения результата!"
    )
    
    keyboard = [
        [InlineKeyboardButton("▶️ Продолжить тест", callback_data="next_question")],
        [InlineKeyboardButton("🔄 Сбросить статистику", callback_data="reset_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=stats_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    await query.answer()


async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user statistics"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await db.quiz_stats.update_one(
        {"user_id": user_id},
        {"$set": {
            "total_answered": 0,
            "correct_answers": 0,
            "wrong_answers": 0,
            "last_activity": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    await query.answer("✅ Статистика сброшена!")
    
    keyboard = [
        [InlineKeyboardButton("🚀 Начать тест заново", callback_data="start_quiz")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="🔄 *Статистика сброшена!*\n\nНажмите кнопку ниже, чтобы начать тест заново.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    data = query.data
    
    if data == "start_quiz" or data == "next_question":
        await show_question(user_id, chat_id, context, message_id)
        await query.answer()
    elif data == "show_stats":
        await show_stats(update, context)
    elif data == "reset_stats":
        await reset_stats(update, context)
    elif data.startswith("answer_"):
        selected_answer = data.replace("answer_", "")
        await handle_answer(update, context, selected_answer)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "📖 *Справка по боту*\n\n"
        "*Команды:*\n"
        "/start - Начать или перезапустить бота\n"
        "/help - Показать эту справку\n"
        "/stats - Показать вашу статистику\n\n"
        "*Как пользоваться:*\n"
        "1. Нажмите 'Начать тест'\n"
        "2. Выберите один из вариантов ответа (A, B, C, D)\n"
        "3. Получите результат и правильный ответ\n"
        "4. Продолжите или посмотрите статистику\n\n"
        "📚 В базе 180 вопросов по проектированию печатных плат!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 Начать тест", callback_data="start_quiz")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    user_id = update.effective_user.id
    
    stats = await get_user_stats(user_id)
    
    total = stats['total_answered']
    correct = stats['correct_answers']
    wrong = stats['wrong_answers']
    
    if total > 0:
        percentage = round(correct / total * 100, 1)
    else:
        percentage = 0
    
    # Determine skill level
    if percentage >= 90:
        level = "🏆 Эксперт"
    elif percentage >= 70:
        level = "🥇 Продвинутый"
    elif percentage >= 50:
        level = "🥈 Средний"
    elif percentage >= 30:
        level = "🥉 Начинающий"
    else:
        level = "📚 Ученик"
    
    stats_text = (
        f"📊 *Ваша статистика*\n\n"
        f"📝 Всего ответов: *{total}*\n"
        f"✅ Правильных: *{correct}*\n"
        f"❌ Неправильных: *{wrong}*\n\n"
        f"📈 Процент правильных: *{percentage}%*\n"
        f"🎯 Уровень: *{level}*"
    )
    
    keyboard = [
        [InlineKeyboardButton("▶️ Продолжить тест", callback_data="next_question")],
        [InlineKeyboardButton("🔄 Сбросить статистику", callback_data="reset_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')


def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start polling
    logger.info("Starting PCB Quiz Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
