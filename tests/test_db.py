"""Offline tests for SQLite storage, using a temporary database file."""

import tempfile
import unittest
from pathlib import Path

import db

USER = 12345


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.original_path = db.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = str(Path(self.temp_dir.name) / "test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_task_lifecycle(self):
        task_id = db.add_task(
            USER,
            "submit lab record",
            "2026-11-05T17:00:00+05:30",
            "none",
        )
        task = db.get_task(task_id)
        self.assertEqual(task["title"], "submit lab record")
        self.assertEqual(task["recurrence"], "none")

        self.assertEqual(len(db.list_open_tasks(USER)), 1)
        self.assertTrue(db.mark_task_done(USER, task_id))
        self.assertEqual(db.list_open_tasks(USER), [])

    def test_todo_is_not_a_timed_reminder(self):
        todo_id = db.add_todo(USER, "buy notebook")
        self.assertIsNone(db.get_task(todo_id)["remind_at"])
        self.assertEqual(len(db.list_open_todos(USER)), 1)

        start = "2026-11-05T00:00:00+05:30"
        end = "2026-11-06T00:00:00+05:30"
        self.assertEqual(db.reminders_between(USER, start, end), [])

    def test_reminders_between_dates(self):
        db.add_task(
            USER, "morning", "2026-11-05T08:00:00+05:30", "daily"
        )
        db.add_task(
            USER, "tomorrow", "2026-11-06T08:00:00+05:30", "none"
        )
        found = db.reminders_between(
            USER,
            "2026-11-05T00:00:00+05:30",
            "2026-11-06T00:00:00+05:30",
        )
        self.assertEqual([row["title"] for row in found], ["morning"])

    def test_reschedule_recurring_task(self):
        task_id = db.add_task(
            USER, "water", "2026-11-05T08:00:00+05:30", "daily"
        )
        db.set_task_remind_at(task_id, "2026-11-06T08:00:00+05:30")
        self.assertEqual(
            db.get_task(task_id)["remind_at"],
            "2026-11-06T08:00:00+05:30",
        )

    def test_habits_and_logs(self):
        self.assertTrue(db.add_habit(USER, "exercise"))
        self.assertFalse(db.add_habit(USER, "Exercise"))

        habits = db.list_habits(USER)
        habit_id = habits[0]["id"]
        self.assertEqual(len(db.pending_habits(USER, "2026-11-05")), 1)

        db.log_habit(habit_id, "2026-11-05", 1)
        self.assertEqual(db.pending_habits(USER, "2026-11-05"), [])
        self.assertEqual(len(db.get_habit_logs(habit_id)), 1)

        db.log_habit(habit_id, "2026-11-05", 0)
        logs = db.get_habit_logs(habit_id)
        self.assertEqual(logs[0]["status"], 0)

    def test_expenses_and_monthly_summary(self):
        db.add_expense(
            USER, 120.0, "Food", "lunch", "2026-11-05T12:30:00+05:30"
        )
        db.add_expense(
            USER, 80.5, "Travel", "bus", "2026-11-05T18:00:00+05:30"
        )
        db.add_expense(
            USER, 500.0, "Study", "book", "2026-10-20T10:00:00+05:30"
        )

        self.assertEqual(db.expense_count(USER), 3)
        self.assertEqual(
            db.spending_on(USER, "2026-11-05"), 200.5
        )

        summary = dict(db.monthly_summary(USER, "2026-11"))
        self.assertEqual(summary["Food"], 120.0)
        self.assertEqual(summary["Travel"], 80.5)
        self.assertNotIn("Study", summary)

        csv_text = db.expenses_csv(USER)
        self.assertIn("date,amount,category,note", csv_text)
        self.assertIn("lunch", csv_text)
        self.assertIn("2026-11-05", csv_text)


if __name__ == "__main__":
    unittest.main()
