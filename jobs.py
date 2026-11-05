"""Scheduled work: reminders, the morning briefing, and habit check-ins."""

import logging
from datetime import date, datetime, timedelta
from datetime import time as dtime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

import config
import db
import utils
import weather

logger = logging.getLogger(__name__)

REMINDER_JOB_PREFIX = "reminder:"

# Don't skip a job just because the event loop was briefly busy.
JOB_KWARGS = {"misfire_grace_time": 3600, "coalesce": True}


# --------------------------------------------------------------------------
# Reminder scheduling
# --------------------------------------------------------------------------

def schedule_reminder(application: Application, task) -> None:
    """Put one reminder in the job queue. Recurring tasks reschedule themselves."""
    if task["remind_at"] is None:
        return

    when = datetime.fromisoformat(task["remind_at"])
    now = utils.now_local()
    if when <= now:
        # If the bot was offline at the scheduled time, fire shortly after startup.
        when = now + timedelta(seconds=2)

    application.job_queue.run_once(
        reminder_job,
        when=when,
        data={"task_id": task["id"]},
        name=f"{REMINDER_JOB_PREFIX}{task['id']}",
        job_kwargs=JOB_KWARGS,
    )


def cancel_reminder_jobs(application: Application, task_id: int) -> None:
    """Remove a pending reminder job when the task is completed by hand."""
    for job in application.job_queue.get_jobs_by_name(
        f"{REMINDER_JOB_PREFIX}{task_id}"
    ):
        job.schedule_removal()


def schedule_all_reminders(application: Application) -> None:
    """Restore reminders from SQLite after a restart (jobs are not persisted)."""
    for task in db.pending_reminders():
        schedule_reminder(application, task)


async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a reminder, then advance or close the task."""
    task_id = context.job.data["task_id"]
    task = db.get_task(task_id)
    if task is None or task["done"]:
        return

    await context.bot.send_message(
        chat_id=task["user_id"],
        text=f"Reminder: {task['title']}",
    )

    recurrence = task["recurrence"]
    if recurrence in ("daily", "weekly"):
        step = timedelta(days=1 if recurrence == "daily" else 7)
        next_when = datetime.fromisoformat(task["remind_at"]) + step
        now = utils.now_local()

        # If the bot missed several days, skip forward to the next future one.
        while next_when <= now:
            next_when += step

        db.set_task_remind_at(task_id, next_when.isoformat())
        fresh_task = db.get_task(task_id)
        if fresh_task is not None:
            schedule_reminder(context.application, fresh_task)
    else:
        db.mark_task_done(task["user_id"], task_id)


# --------------------------------------------------------------------------
# Morning briefing
# --------------------------------------------------------------------------

async def send_briefing(bot, user_id: int) -> None:
    """Build and send the daily briefing (also used by /brief)."""
    now = utils.now_local()
    today = now.date()

    weather_text = await weather.get_weather(config.CITY, config.TIMEZONE)

    day_start = datetime.combine(today, dtime.min, tzinfo=utils.TZ)
    day_end = day_start + timedelta(days=1)
    reminders = db.reminders_between(user_id, day_start.isoformat(), day_end.isoformat())
    todos = db.list_open_todos(user_id)
    pending = db.pending_habits(user_id, today.isoformat())
    yesterday = today - timedelta(days=1)
    yesterday_total = db.spending_on(user_id, yesterday.isoformat())

    lines = [
        f"Good morning! {now.strftime('%A, %d %b %Y')}",
        "",
        f"Weather in {config.CITY}: {weather_text or 'unavailable right now'}",
        "",
        "Today's reminders:",
    ]

    if reminders:
        for task in reminders:
            label = utils.clock(datetime.fromisoformat(task["remind_at"]))
            repeat = (
                f" ({task['recurrence']})"
                if task["recurrence"] != "none"
                else ""
            )
            lines.append(f"- {label} - {task['title']}{repeat}")
    else:
        lines.append("- None")

    lines += ["", "To-dos:"]
    if todos:
        lines.extend(f"- {task['title']}" for task in todos)
    else:
        lines.append("- None")

    habit_names = ", ".join(habit["name"] for habit in pending) or "None"
    lines += [
        "",
        f"Habits pending today: {habit_names}",
        f"Yesterday's spending: {utils.money(yesterday_total)}",
    ]

    await bot.send_message(chat_id=user_id, text="\n".join(lines))


async def briefing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_briefing(context.bot, config.ALLOWED_USER_ID)


# --------------------------------------------------------------------------
# Evening habit check-in and weekly summary
# --------------------------------------------------------------------------

async def send_habit_questions(bot, user_id: int) -> int:
    """Ask one Yes/No question per pending habit. Returns how many were sent."""
    today = utils.now_local().date().isoformat()
    pending = db.pending_habits(user_id, today)

    for habit in pending:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Yes", callback_data=f"habit:yes:{habit['id']}:{today}"
                    ),
                    InlineKeyboardButton(
                        "No", callback_data=f"habit:no:{habit['id']}:{today}"
                    ),
                ]
            ]
        )
        name = habit["name"]
        question_name = name[:1].lower() + name[1:] if name else name
        await bot.send_message(
            chat_id=user_id,
            text=f"Did you {question_name} today?",
            reply_markup=keyboard,
        )

    return len(pending)


async def habit_checkin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """The 9 PM job: only asks about habits not logged yet today."""
    await send_habit_questions(context.bot, config.ALLOWED_USER_ID)


def _current_streak(statuses: dict[date, int], today: date) -> int:
    """Count consecutive 'yes' days. Today may still be unanswered."""
    day = today
    if day not in statuses:
        day -= timedelta(days=1)

    streak = 0
    while statuses.get(day) == 1:
        streak += 1
        day -= timedelta(days=1)
    return streak


def habit_summary_text(user_id: int) -> str:
    """Weekly counts and current streak for every habit."""
    habits = db.list_habits(user_id)
    if not habits:
        return "No habits yet. Add one with /addhabit exercise."

    today = utils.now_local().date()
    week_start = today - timedelta(days=6)

    lines = ["Habit summary (last 7 days):"]
    for habit in habits:
        logs = db.get_habit_logs(habit["id"])
        statuses = {
            date.fromisoformat(row["log_date"]): row["status"] for row in logs
        }

        done = 0
        for offset in range(7):
            if statuses.get(week_start + timedelta(days=offset)) == 1:
                done += 1

        streak = _current_streak(statuses, today)
        plural = "" if streak == 1 else "s"
        lines.append(f"- {habit['name']}: {done}/7, streak {streak} day{plural}")

    return "\n".join(lines)
