import telebot
from telebot import types
import sqlite3
import threading
import time
import requests
import asyncio
import re
from telethon import TelegramClient
from telethon import events

bot = telebot.TeleBot(API_TOKEN)
client = TelegramClient('shop_session', API_ID, API_HASH)

conn = sqlite3.connect('shop.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    category TEXT NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    login TEXT NOT NULL,
    password TEXT NOT NULL,
    phone TEXT,
    attempts INTEGER DEFAULT 3,
    status TEXT DEFAULT 'available',
    monitoring INTEGER DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES products (id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    account_id INTEGER,
    invoice_id TEXT UNIQUE,
    invoice_url TEXT,
    payment_status TEXT DEFAULT 'pending',
    delivery_status TEXT DEFAULT 'waiting',
    attempts_used INTEGER DEFAULT 0,
    attempts_left INTEGER DEFAULT 3,
    code_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    code TEXT,
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
)
''')

conn.commit()

def create_invoice(amount, currency='USDT'):
    url = 'https://pay.crypt.bot/api/createInvoice'
    headers = {'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN}
    data = {
        'amount': str(amount),
        'asset': currency,
        'description': 'Оплата товара в Fiz Shop'
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.json()
    except:
        return {'ok': False}

def check_invoice(invoice_id):
    url = f'https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}'
    headers = {'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json()
    except:
        return {'ok': False}

@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    catalog_btn = types.KeyboardButton('🛒 Каталог')
    support_btn = types.KeyboardButton('🆘 Поддержка')
    markup.add(catalog_btn, support_btn)
    
    bot.send_message(
        message.chat.id,
        f'Привет {user.first_name} добро пожаловать в fiz shop от Alsay!👋',
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '🛒 Каталог')
def catalog(message):
    cursor.execute('SELECT DISTINCT category FROM products WHERE EXISTS (SELECT 1 FROM accounts WHERE accounts.product_id = products.id AND accounts.status = "available")')
    categories = cursor.fetchall()
    
    if not categories:
        bot.send_message(message.chat.id, 'Каталог пуст')
        return
    
    markup = types.InlineKeyboardMarkup()
    for category in categories:
        btn = types.InlineKeyboardButton(text=category[0], callback_data=f'category_{category[0]}')
        markup.add(btn)
    
    bot.send_message(message.chat.id, 'Выберите категорию:', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('category_'))
def show_category_products(call):
    category = call.data.replace('category_', '')
    
    cursor.execute('''
        SELECT p.id, p.name, p.description, p.price 
        FROM products p 
        WHERE p.category = ? AND EXISTS (
            SELECT 1 FROM accounts a 
            WHERE a.product_id = p.id AND a.status = "available"
        )
    ''', (category,))
    products = cursor.fetchall()
    
    if not products:
        bot.answer_callback_query(call.id, 'В этой категории нет товаров')
        return
    
    markup = types.InlineKeyboardMarkup()
    for product in products:
        btn = types.InlineKeyboardButton(
            text=f'{product[1]} - {product[3]}$',
            callback_data=f'product_{product[0]}'
        )
        markup.add(btn)
    
    markup.add(types.InlineKeyboardButton('◀️ Назад', callback_data='back_to_main'))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f'Товары в категории {category}:',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('product_'))
def show_product(call):
    product_id = int(call.data.replace('product_', ''))
    
    cursor.execute('SELECT name, description, price FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    markup = types.InlineKeyboardMarkup()
    buy_btn = types.InlineKeyboardButton(text=f'Купить за {product[2]}$', callback_data=f'buy_{product_id}')
    back_btn = types.InlineKeyboardButton('◀️ Назад', callback_data='back_to_categories')
    markup.add(buy_btn)
    markup.add(back_btn)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f'<b>{product[0]}</b>\n\n{product[1]}\n\nЦена: <b>{product[2]}$</b>',
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_categories')
def back_to_categories(call):
    catalog(call.message)
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    start(call.message)
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def process_payment(call):
    product_id = int(call.data.replace('buy_', ''))
    user_id = call.from_user.id
    
    cursor.execute('SELECT price FROM products WHERE id = ?', (product_id,))
    price = cursor.fetchone()[0]
    
    invoice = create_invoice(price)
    
    if invoice.get('ok'):
        invoice_id = invoice['result']['invoice_id']
        invoice_url = invoice['result']['pay_url']
        
        cursor.execute('''
            INSERT INTO orders (user_id, product_id, invoice_id, invoice_url) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, product_id, invoice_id, invoice_url))
        conn.commit()
        
        markup = types.InlineKeyboardMarkup()
        pay_btn = types.InlineKeyboardButton(text='Оплатить', url=invoice_url)
        check_btn = types.InlineKeyboardButton(text='Проверить оплату', callback_data=f'check_{invoice_id}')
        markup.add(pay_btn)
        markup.add(check_btn)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f'Счет на оплату {price}$\n\nСсылка для оплаты: {invoice_url}',
            reply_markup=markup
        )
        
        threading.Thread(target=monitor_payment, args=(invoice_id, user_id, product_id)).start()
    else:
        bot.answer_callback_query(call.id, 'Ошибка создания счета')

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_'))
def check_payment(call):
    invoice_id = call.data.replace('check_', '')
    user_id = call.from_user.id
    
    cursor.execute('SELECT payment_status FROM orders WHERE invoice_id = ? AND user_id = ?', 
                   (invoice_id, user_id))
    order = cursor.fetchone()
    
    if not order:
        bot.answer_callback_query(call.id, 'Заказ не найден')
        return
    
    if order[0] == 'paid':
        bot.answer_callback_query(call.id, 'Оплата уже подтверждена')
        return
    
    invoice_info = check_invoice(invoice_id)
    
    if invoice_info.get('ok'):
        status = invoice_info['result']['items'][0]['status']
        
        if status == 'paid':
            cursor.execute('UPDATE orders SET payment_status = ? WHERE invoice_id = ?', 
                           ('paid', invoice_id))
            conn.commit()
            
            bot.answer_callback_query(call.id, 'Оплата подтверждена! Выдаем товар...')
            process_order_delivery(invoice_id, user_id)
        else:
            bot.answer_callback_query(call.id, 'Оплата еще не поступила')
    else:
        bot.answer_callback_query(call.id, 'Ошибка проверки платежа')

def process_order_delivery(invoice_id, user_id):
    cursor.execute('''
        SELECT o.id, o.product_id 
        FROM orders o 
        WHERE o.invoice_id = ? AND o.user_id = ? AND o.payment_status = 'paid' AND o.delivery_status = 'waiting'
    ''', (invoice_id, user_id))
    order = cursor.fetchone()
    
    if not order:
        return
    
    order_id, product_id = order
    
    cursor.execute('''
        SELECT id, login, password, phone, attempts 
        FROM accounts 
        WHERE product_id = ? AND status = 'available' 
        LIMIT 1
    ''', (product_id,))
    account = cursor.fetchone()
    
    if not account:
        bot.send_message(user_id, 'Товар временно отсутствует')
        return
    
    account_id, login, password, phone, attempts = account
    
    cursor.execute('UPDATE accounts SET status = ?, monitoring = 1 WHERE id = ?', ('sold', account_id))
    cursor.execute('UPDATE orders SET account_id = ?, delivery_status = ? WHERE id = ?', 
                   (account_id, 'delivered', order_id))
    conn.commit()
    
    if phone:
        threading.Thread(target=start_monitoring, args=(phone, account_id, order_id)).start()
    
    delivery_text = f'''
✅ Товар выдан!

📱 Номер: <code>{login}</code>
🔑 Пароль: <code>{password}</code>

🔄 Попыток входа: {attempts}/3

✅ После входа нажмите кнопку "Подтвердить вход"
'''
    
    markup = types.InlineKeyboardMarkup()
    confirm_btn = types.InlineKeyboardButton(text='✅ Подтвердить вход', callback_data=f'confirm_{order_id}')
    markup.add(confirm_btn)
    
    bot.send_message(user_id, delivery_text, parse_mode='HTML', reply_markup=markup)

def start_monitoring(phone, account_id, order_id):
    async def monitor():
        try:
            await client.start(phone=phone)
            
            @client.on(events.NewMessage)
            async def handler(event):
                if event.is_private:
                    message_text = event.message.text
                    codes = re.findall(r'\b\d{4,8}\b', message_text)
                    
                    if codes:
                        code = codes[0]
                        
                        cursor.execute('''
                            INSERT INTO codes (order_id, account_id, code) 
                            VALUES (?, ?, ?)
                        ''', (order_id, account_id, code))
                        conn.commit()
                        
                        cursor.execute('SELECT user_id FROM orders WHERE id = ?', (order_id,))
                        buyer_id = cursor.fetchone()[0]
                        
                        if buyer_id:
                            bot.send_message(
                                buyer_id,
                                f'🔐 Код подтверждения: <code>{code}</code>\n\n✅ Используйте этот код для завершения входа',
                                parse_mode='HTML'
                            )
            
            await client.run_until_disconnected()
        except Exception as e:
            print(f'Monitoring error: {e}')
    
    asyncio.run(monitor())

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_'))
def confirm_login(call):
    order_id = int(call.data.replace('confirm_', ''))
    user_id = call.from_user.id
    
    cursor.execute('SELECT attempts_used, attempts_left FROM orders WHERE id = ? AND user_id = ?', 
                   (order_id, user_id))
    order = cursor.fetchone()
    
    if not order:
        bot.answer_callback_query(call.id, 'Заказ не найден')
        return
    
    attempts_used, attempts_left = order
    
    if attempts_left <= 0:
        bot.answer_callback_query(call.id, 'Попытки закончились')
        return
    
    new_attempts_used = attempts_used + 1
    new_attempts_left = attempts_left - 1
    
    cursor.execute('''
        UPDATE orders 
        SET attempts_used = ?, attempts_left = ? 
        WHERE id = ?
    ''', (new_attempts_used, new_attempts_left, order_id))
    
    cursor.execute('''
        UPDATE accounts 
        SET attempts = attempts - 1 
        WHERE id = (SELECT account_id FROM orders WHERE id = ?)
    ''', (order_id,))
    
    conn.commit()
    
    if new_attempts_left > 0:
        bot.answer_callback_query(
            call.id, 
            f'✅ Вход подтвержден! Попыток осталось: {new_attempts_left}/3'
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f'✅ Вход подтвержден!\n\n🔄 Попыток использовано: {new_attempts_used}/3\n🔄 Попыток осталось: {new_attempts_left}/3\n\n⏳ Ожидайте код подтверждения...',
            parse_mode='HTML'
        )
    else:
        bot.answer_callback_query(call.id, '✅ Вход подтвержден! Попытки закончились')
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text='✅ Вход завершен!\n\n🔄 Все попытки использованы\n\n⏳ Ожидайте код подтверждения...',
            parse_mode='HTML'
        )

def monitor_payment(invoice_id, user_id, product_id):
    for _ in range(90):
        invoice_info = check_invoice(invoice_id)
        
        if invoice_info.get('ok'):
            status = invoice_info['result']['items'][0]['status']
            
            if status == 'paid':
                cursor.execute('UPDATE orders SET payment_status = ? WHERE invoice_id = ?', 
                               ('paid', invoice_id))
                conn.commit()
                process_order_delivery(invoice_id, user_id)
                return
        
        time.sleep(10)
    
    bot.send_message(user_id, 'Время оплаты истекло')

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id !=ADMIN_ID:
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    add_product_btn = types.KeyboardButton('➕ Добавить товар')
    add_account_btn = types.KeyboardButton('📝 Добавить аккаунт')
    markup.add(add_product_btn, add_account_btn)
    
    bot.send_message(message.chat.id, 'Админ панель', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '➕ Добавить товар')
def add_product_step1(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    msg = bot.send_message(message.chat.id, 'Введите данные товара в формате:\nНазвание:Описание:Цена:Категория')
    bot.register_next_step_handler(msg, add_product_step2)

def add_product_step2(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        data = message.text.split(':')
        if len(data) == 4:
            name, description, price, category = data
            
            cursor.execute('''
                INSERT INTO products (name, description, price, category) 
                VALUES (?, ?, ?, ?)
            ''', (name.strip(), description.strip(), float(price.strip()), category.strip()))
            conn.commit()
            
            bot.send_message(message.chat.id, '✅ Товар добавлен')
        else:
            bot.send_message(message.chat.id, '❌ Неверный формат')
    except:
        bot.send_message(message.chat.id, '❌ Ошибка добавления')

@bot.message_handler(func=lambda message: message.text == '📝 Добавить аккаунт')
def add_account_step1(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    cursor.execute('SELECT id, name FROM products')
    products = cursor.fetchall()
    
    markup = types.InlineKeyboardMarkup()
    for product in products:
        btn = types.InlineKeyboardButton(text=product[1], callback_data=f'addacc_{product[0]}')
        markup.add(btn)
    
    bot.send_message(message.chat.id, 'Выберите товар для добавления аккаунта:', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('addacc_'))
def add_account_step2(call):
    if call.from_user.id !=ADMIN_ID:
        return
    
    product_id = int(call.data.replace('addacc_', ''))
    
    msg = bot.send_message(call.message.chat.id, 'Введите данные аккаунта в формате:\nЛогин:Пароль:Телефон\n\nТелефон нужен для мониторинга кодов после покупки')
    bot.register_next_step_handler(msg, add_account_step3, product_id)

def add_account_step3(message, product_id):
    if message.from_user.id !=ADMIN_ID:
        return
    
    try:
        data = message.text.split(':')
        if len(data) >= 2:
            login = data[0].strip()
            password = data[1].strip()
            phone = data[2].strip() if len(data) > 2 else ''
            
            cursor.execute('''
                INSERT INTO accounts (product_id, login, password, phone) 
                VALUES (?, ?, ?, ?)
            ''', (product_id, login, password, phone))
            conn.commit()
            
            response_text = f'''
✅ Аккаунт добавлен!

Логин: <code>{login}</code>
Пароль: <code>{password}</code>
Телефон: {phone if phone else 'Не указан'}
Попыток входа: 3/3
'''
            
            bot.send_message(message.chat.id, response_text, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, '❌ Неверный формат')
    except:
        bot.send_message(message.chat.id, '❌ Ошибка добавления')

@bot.message_handler(func=lambda message: message.text == '🆘 Поддержка')
def support(message):
    bot.send_message(message.chat.id, 'Поддержка: @AlsaySupport')

if __name__ == '__main__':
    print('Бот запущен...')
    bot.polling(none_stop=True)