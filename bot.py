import os
import json
import random
import asyncio
import hashlib
import hmac
from urllib.parse import parse_qs

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, WebAppInfo
)
from aiogram.filters import Command
from dotenv import load_dotenv
from aiohttp import web

import database as db

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://yourusername.github.io/your-repo/")
API_PORT = int(os.getenv("API_PORT", "8081"))
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")   # "*" для разработки

bot = Bot(token=TOKEN)
dp = Dispatcher()

TASK_REWARDS = {
    "robot_win":  {"b": 100, "s": 25,  "game": "robot", "text": "Миссия робота",           "won": True},
    "ttt_win":    {"b": 50,  "s": 15,  "game": "ttt",   "text": "Крестики-нолики: победа", "won": True},
    "ttt_lose":   {"b": 0,   "s": 0,   "game": "ttt",   "text": "Крестики-нолики: поражение","won": False},
    "ttt_draw":   {"b": 5,   "s": 2,   "game": "ttt",   "text": "Крестики-нолики: ничья",  "won": False},
    "rps_win":    {"b": 5,   "s": 10,  "game": "rps",   "text": "К-Н-Б: победа",           "won": True},
    "rps_draw":   {"b": 0,   "s": 2,   "game": "rps",   "text": "К-Н-Б: ничья",            "won": False},
    "rps_lose":   {"b": 0,   "s": 0,   "game": "rps",   "text": "К-Н-Б: поражение",        "won": False},
}

SECRET_KEY = hashlib.sha256(TOKEN.encode()).digest()


def validate_init_data(init_data: str):
    """HMAC-SHA256 проверка initData (стандарт Telegram)"""
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        items = [(k, v[0]) for k, v in parsed.items() if k != "hash"]
        items.sort()
        data_check = "\n".join(f"{k}={v}" for k, v in items)

        computed = hmac.new(SECRET_KEY, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, received_hash):
            return None

        user_str = parsed.get("user", [None])[0]
        return json.loads(user_str) if user_str else None
    except Exception:
        return None


def cors_headers():
    return {
        "Access-Control-Allow-Origin": CORS_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "3600",
    }


def _ensure_user(user_id, user_obj):
    username = user_obj.get("username") or user_obj.get("first_name") or "Аноним"
    db.get_user(user_id, username)
    if user_obj.get("photo_url"):
        db.save_avatar(user_id, user_obj["photo_url"])


# ====================================

db.init_db()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Аноним"
    db.get_user(user_id, username)
    await message.answer(
        f"Здравствуй! Я - развлекательный бот команды Лиги Инженеров "
        f"<a href='https://t.me'>Quantum Spirit 33472</a>. "
        f"Ты можешь играть с ботом, другими людьми или своими друзьями и зарабатывать очки!\n\n"
        f"Нажми кнопку 'Меню', отправь команду /menu или зайди в Приложение по кнопке рядом с полем ввода, "
        f"чтобы перейти в главное меню.",
        parse_mode="HTML"
    )


@dp.message(Command("top"))
async def cmd_top(message: Message):
    top = db.get_top()
    if not top:
        await message.answer("Таблица Лидеров пока что пуста. Заработайте первые очки!")
        return
    text = "🏆 **ТОП-10 ИГРОКОВ ПО ОЧКАМ:**\n\n"
    for i, (name, score) in enumerate(top, 1):
        text += f"{i}. @{name} - {score} P\n"
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("rps"))
async def cmd_rps(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🪨 Камень", callback_data="rps_rock"),
        InlineKeyboardButton(text="✂️ Ножницы", callback_data="rps_scissors"),
        InlineKeyboardButton(text="📄 Бумага", callback_data="rps_paper"),
    ]])
    await message.answer("**Ваш выбор?**", reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("rps_"))
async def rps_result(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_choice = callback.data.split("_")[1]
    bot_choice = random.choice(['rock', 'paper', 'scissors'])
    ru = {"rock": "🪨 Камень", "scissors": "✂️ Ножницы", "paper": "📄 Бумага"}

    if user_choice == bot_choice:
        task = "rps_draw"
        result_text = "Ничья! +2 очка опыта."
    elif (user_choice == "rock" and bot_choice == "scissors") or \
         (user_choice == "scissors" and bot_choice == "paper") or \
         (user_choice == "paper" and bot_choice == "rock"):
        task = "rps_win"
        result_text = "Ты победил! +10 очков опыта, +5 валюты"
    else:
        task = "rps_lose"
        result_text = "Робот победил! Очки не начислены."

    r = TASK_REWARDS[task]
    db.update_balance(user_id, r["b"], r["s"], "reward", r["text"])
    db.update_game(user_id, r["game"], r["won"])

    after = (
        f"**Твой выбор:** {ru[user_choice]}\n"
        f"**Выбор робота:** {ru[bot_choice]}\n\n"
        f"**{result_text}**"
    )
    await callback.message.edit_text(after, parse_mode="Markdown")


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🤖 Открыть Приложение", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await message.answer("Вы можете открыть приложение по кнопке ниже:", reply_markup=kb)


@dp.message(F.web_app_data)
async def web_app_receive(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
        task = data.get("task")
        if not task or task not in TASK_REWARDS:
            await message.answer("⚠️ Неизвестная задача.")
            return
        r = TASK_REWARDS[task]
        db.update_balance(message.from_user.id, r["b"], r["s"], "reward", r["text"])
        db.update_game(message.from_user.id, r["game"], r["won"])
        if r["b"] > 0 or r["s"] > 0:
            await message.answer(
                f"✅ Задание выполнено!\n\n💰 +{r['b']} тех-коинов\n✨ +{r['s']} XP"
            )
    except Exception:
        await message.answer("⚠️ Ошибка синхронизации данных из Приложения.")


# ==================================== aiohttp

async def api_options(request):
    return web.Response(status=204, headers=cors_headers())


async def api_me(request):
    init_data = request.query.get("initData", "")
    user = validate_init_data(init_data)
    if not user:
        return web.json_response({"error": "invalid_init_data"}, status=401, headers=cors_headers())

    _ensure_user(user["id"], user)
    db.update_streak(user["id"])
    profile = db.get_user_full(user["id"])
    return web.json_response(profile, headers=cors_headers())


async def api_top(request):
    return web.json_response(db.get_top_full(), headers=cors_headers())


async def api_task(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_json"}, status=400, headers=cors_headers())

    user = validate_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"error": "invalid_init_data"}, status=401, headers=cors_headers())

    task = body.get("task")
    if not task or task not in TASK_REWARDS:
        return web.json_response({"error": "unknown_task"}, status=400, headers=cors_headers())

    r = TASK_REWARDS[task]
    _ensure_user(user["id"], user)
    db.update_balance(user["id"], r["b"], r["s"], "reward", r["text"])
    db.update_game(user["id"], r["game"], r["won"])

    return web.json_response({
        "ok": True, "b_change": r["b"], "s_change": r["s"],
    }, headers=cors_headers())


async def run_api():
    app = web.Application()
    app.router.add_route("OPTIONS", "/api/{path:.*}", api_options)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/top", api_top)
    app.router.add_post("/api/task", api_task)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", API_PORT)
    await site.start()
    print(f"API server running on http://localhost:{API_PORT}")


# ====================================

async def main():
    print("Bot is now starting.")
    await asyncio.gather(
        run_api(),
        dp.start_polling(bot)
    )


if __name__ == "__main__":
    asyncio.run(main())
