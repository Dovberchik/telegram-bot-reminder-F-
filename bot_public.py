
import logging
import os
import json
import threading
import time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
import dateparser
import re

# === НАСТРОЙКИ ===
TOKEN = os.environ["BOT_TOKEN"]
TASKS_FILE = "tasks.json"
WAITING_FOR_REMINDER_TIME = range(1)

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

def add_task(text, dt, remind_before, user_id):
    tasks = load_tasks()
    task = {
        "text": text,
        "time": dt.isoformat(),
        "user_id": user_id,
        "notified": False,
        "remind_before": remind_before
    }
    tasks.append(task)
    save_tasks(tasks)

def extract_datetime(text: str):
    parsed = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "DATE_ORDER": "DMY",
            "RELATIVE_BASE": datetime.now()
        },
        languages=["ru"]
    )
    if parsed:
        return parsed

    match = re.search(r"(\d{1,2}[./]\d{1,2})\s*(в\s*)?(\d{1,2}:\d{2})", text)
    if match:
        date_str = match.group(1)
        time_str = match.group(3)
        current_year = datetime.now().year
        full_str = f"{date_str}.{current_year} {time_str}"
        try:
            return datetime.strptime(full_str, "%d.%m.%Y %H:%M")
        except:
            try:
                return datetime.strptime(full_str, "%d/%m/%Y %H:%M")
            except:
                return None
    return None

# === ОБРАБОТКА ===
user_temp = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or update.effective_user.first_name
    await update.message.reply_text(f"Привет, @{username}! Я помогу напоминать о ваших задачах.\nПросто напиши что-то вроде: 'Позвонить врачу 12.05.2025 в 18:00'")

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = load_tasks()
    response = "📋 Ваши задачи:\n"
    for i, task in enumerate(tasks):
        if task["user_id"] == update.effective_user.id:
            dt = datetime.fromisoformat(task["time"]).strftime("%d.%m %H:%M")
            mark = "✅" if task["notified"] else "❗"
            response += f"{mark} {i+1}. {task['text']} — {dt} (за {task['remind_before']} мин)\n"
    await update.message.reply_text(response.strip() or "Задач пока нет.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    dt = extract_datetime(text)
    print(f"[DEBUG] '{text}' => {dt}")
    if dt:
        user_temp[update.effective_user.id] = {"text": text, "dt": dt}
        await update.message.reply_text("⏰ За сколько минут до события напомнить?")
        return WAITING_FOR_REMINDER_TIME
    else:
        await update.message.reply_text("⛔️ Не смог разобрать дату/время. Попробуй в формате '12.05.2025 в 18:00'.")

async def handle_remind_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_temp:
        await update.message.reply_text("Что-то пошло не так. Попробуй сначала.")
        return ConversationHandler.END
    try:
        minutes = int(update.message.text.strip())
        data = user_temp.pop(uid)
        add_task(data["text"], data["dt"], minutes, uid)
        remind_time = data["dt"] - timedelta(minutes=minutes)
        await update.message.reply_text(
            f"✅ Задача добавлена: '{data['text']}'\n🔔 Напоминание будет в {remind_time.strftime('%d.%m %H:%M')}"
        )
    except ValueError:
        await update.message.reply_text("⛔️ Введи количество минут числом, например: 15")
        return WAITING_FOR_REMINDER_TIME
    return ConversationHandler.END

def reminder_loop(application):
    while True:
        tasks = load_tasks()
        now = datetime.now()
        changed = False
        for task in tasks:
            if not task["notified"]:
                remind_at = datetime.fromisoformat(task["time"]) - timedelta(minutes=task["remind_before"])
                if now >= remind_at:
                    application.bot.send_message(chat_id=task["user_id"], text=f"🔔 Напоминание: {task['text']}")
                    task["notified"] = True
                    changed = True
        if changed:
            save_tasks(tasks)
        time.sleep(30)

def main():
    logging.basicConfig(level=logging.INFO)
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler)],
        states={WAITING_FOR_REMINDER_TIME: [MessageHandler(filters.TEXT, handle_remind_time)]},
        fallbacks=[],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tasks", show_tasks))
    application.add_handler(conv_handler)

    threading.Thread(target=reminder_loop, args=(application,), daemon=True).start()
    application.run_polling()

if __name__ == "__main__":
    main()
