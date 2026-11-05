"""DayPilot: a personal Telegram bot for reminders, briefings, habits, and expenses."""

import logging
from datetime import datetime
from datetime import time as dtime
from io import BytesIO

from telegram import BotCommand, InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import db
import jobs
import parsers
import utils

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Security gate: only your Telegram account. Commands also require a private chat.
AUTH = filters.User(user_id=config.ALLOWED_USER_ID)
PRIVATE_AUTH = AUTH & filters.ChatType.PRIVATE

HELP_TEXT = (
    "I'm DayPilot. I handle reminders, habits, and expenses.\n\n"
    "Natural messages:\n"
    "remind me to submit the lab record at 5pm\n"
    "remind me to drink water daily at 8am\n"
    "remind me to clean my room every Sunday at 11am\n"
    "spent 120 on lunch\n\n"
    "Commands:\n"
    "/brief - Morning briefing now\n"
    "/tasks - Open reminders and to-dos\n"
    "/done <id> - Complete a task\n"
    "/todo <text> - Add a to-do\n"
    "/addhabit <name> - Add a habit\n"
    "/checkin - Ask habit questions now\n"
    "/habits - Weekly habit summary\n"
    "/report [YYYY-MM] - Monthly expense summary\n"
    "/export - Download expenses as CSV\n"
    "/help - This message"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hi! I'm ready.\n\n" + HELP_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def handle_reminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    try:
        parsed = parsers.parse_reminder(text)
    except parsers.ParseError as exc:
        await update.message.reply_text(str(exc))
        return

    task_id = db.add_task(
        update.effective_user.id,
        parsed.title,
        parsed.when.isoformat(),
        parsed.recurrence,
    )
    task = db.get_task(task_id)
    if task is not None:
        jobs.schedule_reminder(context.application, task)

    if parsed.recurrence == "daily":
        message = f"Done! Daily reminder set for {utils.clock(parsed.when)}."
    elif parsed.recurrence == "weekly":
        message = (
            f"Done! Weekly reminder set for {utils.describe_when(parsed.when)}."
        )
    else:
        message = f"Done! Reminder set for {utils.describe_when(parsed.when)}."

    await update.message.reply_text(message)


async def handle_expense(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    try:
        parsed = parsers.parse_expense(text)
    except parsers.ParseError as exc:
        await update.message.reply_text(str(exc))
        return

    db.add_expense(
        update.effective_user.id,
        parsed.amount,
        parsed.category,
        parsed.note,
        utils.now_local().isoformat(timespec="seconds"),
    )
    await update.message.reply_text(
        f"Logged: {utils.money(parsed.amount)}, {parsed.category}."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return

    if text.lower().startswith("remind"):
        await handle_reminder(update, context, text)
    elif parsers.looks_like_expense(text):
        await handle_expense(update, context, text)
    else:
        await update.message.reply_text(
            "Try: 'remind me to ... at 5pm' or 'spent 120 on lunch'. /help"
        )


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_chat_action(ChatAction.TYPING)
    await jobs.send_briefing(context.bot, update.effective_user.id)


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tasks = db.list_open_tasks(update.effective_user.id)
    if not tasks:
        await update.message.reply_text(
            "No open tasks. Add one with: remind me to ... at 5pm"
        )
        return

    lines = ["Open tasks:"]
    for task in tasks:
        if task["remind_at"]:
            label = utils.task_time_label(task["remind_at"])
            repeat = (
                f" ({task['recurrence']})"
                if task["recurrence"] != "none"
                else ""
            )
            lines.append(f"#{task['id']} {label} - {task['title']}{repeat}")
        else:
            lines.append(f"#{task['id']} To-do - {task['title']}")

    await update.message.reply_text("\n".join(lines))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Send the task number, e.g. /done 3.")
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Task numbers are numbers, e.g. /done 3.")
        return

    task = db.get_task(task_id)
    if task is None or task["user_id"] != update.effective_user.id:
        await update.message.reply_text("I couldn't find that task.")
        return

    db.mark_task_done(update.effective_user.id, task_id)
    jobs.cancel_reminder_jobs(context.application, task_id)
    await update.message.reply_text(f"Done: {task['title']}.")


async def todo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    title = " ".join(context.args).strip()
    if not title:
        await update.message.reply_text(
            "What should I add? Example: /todo buy notebook."
        )
        return

    db.add_todo(update.effective_user.id, title)
    await update.message.reply_text(f"Added to your to-dos: {title}.")


async def addhabit_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text(
            "What habit? Example: /addhabit exercise."
        )
        return

    if db.add_habit(update.effective_user.id, name):
        await update.message.reply_text(f"Habit added: {name}.")
    else:
        await update.message.reply_text("That habit is already on your list.")


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sent = await jobs.send_habit_questions(
        context.bot, update.effective_user.id
    )
    if sent == 0:
        if db.list_habits(update.effective_user.id):
            await update.message.reply_text(
                "All habits are already logged for today."
            )
        else:
            await update.message.reply_text(
                "No habits yet. Add one with /addhabit exercise."
            )


async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(jobs.habit_summary_text(update.effective_user.id))


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    month = context.args[0] if context.args else utils.now_local().strftime("%Y-%m")

    try:
        parsed_month = datetime.strptime(month, "%Y-%m")
    except ValueError:
        await update.message.reply_text("Use /report or /report 2026-10.")
        return

    month = parsed_month.strftime("%Y-%m")
    summary = db.monthly_summary(update.effective_user.id, month)
    label = parsed_month.strftime("%b %Y")
    if not summary:
        await update.message.reply_text(f"No expenses recorded for {label} yet.")
        return

    lines = [f"Expenses for {label}:"]
    total = 0.0
    for category, amount in summary:
        lines.append(f"{category}: {utils.money(amount)}")
        total += amount
    lines.append(f"Total: {utils.money(total)}")

    await update.message.reply_text("\n".join(lines))


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if db.expense_count(update.effective_user.id) == 0:
        await update.message.reply_text("No expenses to export yet.")
        return

    csv_text = db.expenses_csv(update.effective_user.id)
    filename = f"daypilot_expenses_{utils.now_local():%Y-%m-%d}.csv"
    document = InputFile(BytesIO(csv_text.encode("utf-8-sig")), filename=filename)
    await update.message.reply_document(
        document=document,
        caption="Your expenses CSV.",
    )


async def habit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    # CallbackQueryHandler has no filter argument in PTB v22, so check here.
    if (
        update.effective_user is None
        or update.effective_user.id != config.ALLOWED_USER_ID
    ):
        return

    parts = (query.data or "").split(":")
    if len(parts) != 4 or parts[1] not in ("yes", "no"):
        return

    try:
        habit_id = int(parts[2])
    except ValueError:
        return

    habit = db.get_habit(habit_id)
    if habit is None or habit["user_id"] != update.effective_user.id:
        await query.edit_message_text("I couldn't find that habit.")
        return

    status = 1 if parts[1] == "yes" else 0
    log_date = parts[3]
    db.log_habit(habit_id, log_date, status)
    answer = "Yes" if status else "No"
    if log_date == utils.now_local().date().isoformat():
        await query.edit_message_text(f"{habit['name']}: {answer}, logged.")
    else:
        await query.edit_message_text(
            f"{habit['name']}: {answer}, logged for {log_date}."
        )


async def post_init(application: Application) -> None:
    """Runs once after the bot is built and before polling starts."""
    if application.job_queue is None:
        raise RuntimeError(
            "Job queue unavailable. Install python-telegram-bot[job-queue]."
        )

    jobs.schedule_all_reminders(application)

    # Times are timezone-aware, so PTB schedules them in Asia/Kolkata.
    application.job_queue.run_daily(
        jobs.briefing_job,
        time=dtime(7, 0, tzinfo=utils.TZ),
        name="daily_briefing",
        job_kwargs=jobs.JOB_KWARGS,
    )
    application.job_queue.run_daily(
        jobs.habit_checkin_job,
        time=dtime(21, 0, tzinfo=utils.TZ),
        name="habit_checkin",
        job_kwargs=jobs.JOB_KWARGS,
    )

    try:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Show help"),
                BotCommand("brief", "Morning briefing now"),
                BotCommand("tasks", "Open reminders and to-dos"),
                BotCommand("done", "Complete a task by number"),
                BotCommand("todo", "Add a to-do"),
                BotCommand("addhabit", "Add a habit"),
                BotCommand("checkin", "Ask habit questions now"),
                BotCommand("habits", "Weekly habit summary"),
                BotCommand("report", "Monthly expense summary"),
                BotCommand("export", "Download expenses as CSV"),
                BotCommand("help", "Show help"),
            ]
        )
    except Exception:
        logger.warning("Could not register commands with Telegram.", exc_info=True)


async def error_handler(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error: %s", context.error, exc_info=context.error)


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "Missing BOT_TOKEN. Copy .env.example to .env and paste your token."
        )
    if config.ALLOWED_USER_ID <= 0:
        raise SystemExit(
            "Missing ALLOWED_USER_ID. Copy .env.example to .env and paste your id."
        )

    db.init_db()

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start, filters=PRIVATE_AUTH))
    application.add_handler(CommandHandler("help", help_command, filters=PRIVATE_AUTH))
    application.add_handler(CommandHandler("brief", brief, filters=PRIVATE_AUTH))
    application.add_handler(CommandHandler("tasks", tasks_command, filters=PRIVATE_AUTH))
    application.add_handler(CommandHandler("done", done_command, filters=PRIVATE_AUTH))
    application.add_handler(CommandHandler("todo", todo_command, filters=PRIVATE_AUTH))
    application.add_handler(
        CommandHandler("addhabit", addhabit_command, filters=PRIVATE_AUTH)
    )
    application.add_handler(
        CommandHandler("checkin", checkin_command, filters=PRIVATE_AUTH)
    )
    application.add_handler(
        CommandHandler("habits", habits_command, filters=PRIVATE_AUTH)
    )
    application.add_handler(
        CommandHandler("report", report_command, filters=PRIVATE_AUTH)
    )
    application.add_handler(
        CommandHandler("export", export_command, filters=PRIVATE_AUTH)
    )
    application.add_handler(
        CallbackQueryHandler(
            habit_callback,
            pattern=r"^habit:(?:yes|no):\d+:\d{4}-\d{2}-\d{2}$",
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & PRIVATE_AUTH, handle_text)
    )
    application.add_error_handler(error_handler)

    logger.info("DayPilot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
