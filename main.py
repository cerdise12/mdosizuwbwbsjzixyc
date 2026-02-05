import asyncio
import uuid
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ChatMemberUpdated
)
from aiogram.filters import Command

# ====== НАСТРОЙКИ ======
BOT_TOKEN = "8215857442:AAHf6x9GS2NpkKp8IN-EsVX7JtnrrrXROwI"
CRYPTO_TOKEN = "440089:AA3xARIrC9YPZv61EZPA4VsBLacwHUqBTIg"
GROUP_ID = -5229913068

CRYPTO_API = "https://pay.crypt.bot/api"
PRICE_USDT = "0.1"   # 🔥 минималка Crypto Bot
KICK_DELAY = 60      # ⏱ 1 минута
# ======================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# временное хранилище
invoices = {}     # invoice_id -> user_id
entered_users = {}  # user_id -> True

# ---------- UI ----------
def buy_keyboard(pay_url: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💸 Оплатить USDT", url=pay_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data="check")]
        ]
    )

def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить доступ", callback_data="buy")]
        ]
    )

# ---------- Crypto ----------
async def create_invoice(user_id: int):
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": PRICE_USDT,
        "description": "Доступ в приват на 1 минуту",
        "payload": str(user_id)
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CRYPTO_API}/createInvoice", json=payload, headers=headers)
        data = r.json()["result"]
        invoices[data["invoice_id"]] = user_id
        return data

async def check_invoice(invoice_id: int):
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{CRYPTO_API}/getInvoices?invoice_ids={invoice_id}",
            headers=headers
        )
        return r.json()["result"]["items"][0]

# ---------- Хендлеры ----------
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 <b>Приватный доступ</b>\n\n"
        "💰 Цена: <b>0.1 USDT</b>\n"
        "⏱ Доступ: <b>1 минута</b>\n\n"
        "После оплаты ты получишь ссылку 🔗",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "buy")
async def buy(call):
    invoice = await create_invoice(call.from_user.id)

    await call.message.edit_text(
        "💸 <b>Оплата через Crypto Bot</b>\n\n"
        "Нажми кнопку ниже и оплати.\n"
        "После оплаты — жми «Проверить оплату» ✅",
        reply_markup=buy_keyboard(invoice["pay_url"]),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check")
async def check(call):
    user_id = call.from_user.id
    invoice_id = next((i for i, u in invoices.items() if u == user_id), None)

    if not invoice_id:
        await call.answer("❌ Счёт не найден", show_alert=True)
        return

    invoice = await check_invoice(invoice_id)

    if invoice["status"] != "paid":
        await call.answer("⏳ Оплата не найдена", show_alert=True)
        return

    # выдаём ссылку
    invite = await bot.create_chat_invite_link(
        chat_id=GROUP_ID,
        member_limit=1
    )

    await call.message.edit_text(
        "✅ <b>Оплата получена!</b>\n\n"
        "🔗 Вот твоя ссылка (1 вход):\n"
        f"{invite.invite_link}\n\n"
        "⏱ После входа таймер пойдёт на 1 минуту",
        parse_mode="HTML"
    )

# ---------- Отслеживание входа ----------
@dp.chat_member()
async def on_join(event: ChatMemberUpdated):
    if event.chat.id != GROUP_ID:
        return

    if event.new_chat_member.status == "member":
        user_id = event.from_user.id

        if user_id in entered_users:
            return

        entered_users[user_id] = True
        asyncio.create_task(kick_later(user_id))

async def kick_later(user_id: int):
    await asyncio.sleep(KICK_DELAY)
    try:
        await bot.ban_chat_member(GROUP_ID, user_id)
        await bot.unban_chat_member(GROUP_ID, user_id)
        await bot.send_message(user_id, "⏰ Время доступа истекло.")
    except:
        pass

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
