"""Offline tests for the regex parsers. Run from the project folder.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import parsers

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=TZ)  # Thursday, 10:00 AM


class ReminderParserTests(unittest.TestCase):
    def test_simple_reminder_today(self):
        parsed = parsers.parse_reminder(
            "remind me to submit the lab record at 5pm", now=NOW
        )
        self.assertEqual(parsed.title, "submit the lab record")
        self.assertEqual(parsed.when, datetime(2026, 11, 5, 17, 0, tzinfo=TZ))
        self.assertEqual(parsed.recurrence, "none")

    def test_reminder_with_minutes_and_24h_time(self):
        parsed = parsers.parse_reminder(
            "remind me to take medicine at 21:30", now=NOW
        )
        self.assertEqual(parsed.when, datetime(2026, 11, 5, 21, 30, tzinfo=TZ))

    def test_time_can_come_before_the_task(self):
        parsed = parsers.parse_reminder(
            "remind me at 6pm to submit the lab record", now=NOW
        )
        self.assertEqual(parsed.title, "submit the lab record")
        self.assertEqual(parsed.when, datetime(2026, 11, 5, 18, 0, tzinfo=TZ))

    def test_tomorrow_reminder(self):
        parsed = parsers.parse_reminder(
            "remind me to call mom tomorrow at 9am", now=NOW
        )
        self.assertEqual(parsed.title, "call mom")
        self.assertEqual(parsed.when, datetime(2026, 11, 6, 9, 0, tzinfo=TZ))

    def test_passed_time_rolls_to_tomorrow(self):
        parsed = parsers.parse_reminder(
            "remind me to call mom at 8am", now=NOW
        )
        self.assertEqual(parsed.when, datetime(2026, 11, 6, 8, 0, tzinfo=TZ))

    def test_explicit_today_in_the_past_is_rejected(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_reminder("remind me to call mom today at 8am", now=NOW)

    def test_daily_reminder(self):
        parsed = parsers.parse_reminder(
            "remind me to drink water daily at 8am", now=NOW
        )
        self.assertEqual(parsed.title, "drink water")
        self.assertEqual(parsed.recurrence, "daily")
        self.assertEqual(parsed.when, datetime(2026, 11, 6, 8, 0, tzinfo=TZ))

    def test_weekly_reminder_on_named_day(self):
        parsed = parsers.parse_reminder(
            "remind me to clean my room every Sunday at 11am", now=NOW
        )
        self.assertEqual(parsed.title, "clean my room")
        self.assertEqual(parsed.recurrence, "weekly")
        self.assertEqual(parsed.when, datetime(2026, 11, 8, 11, 0, tzinfo=TZ))

    def test_missing_am_pm_asks_a_question(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_reminder("remind me to call mom at 5", now=NOW)

    def test_missing_time_asks_a_question(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_reminder("remind me to call mom", now=NOW)

    def test_invalid_time(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_reminder("remind me to call mom at 13pm", now=NOW)

    def test_monthly_is_not_supported(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_reminder(
                "remind me to pay rent monthly at 10am", now=NOW
            )


class ExpenseParserTests(unittest.TestCase):
    def test_food(self):
        parsed = parsers.parse_expense("spent 120 on lunch")
        self.assertEqual(parsed.amount, 120)
        self.assertEqual(parsed.category, "Food")
        self.assertEqual(parsed.note, "lunch")

    def test_rupee_symbol_and_travel(self):
        parsed = parsers.parse_expense("spent ₹250 on bus")
        self.assertEqual(parsed.amount, 250)
        self.assertEqual(parsed.category, "Travel")

    def test_study(self):
        self.assertEqual(
            parsers.parse_expense("spent 500 on notebook").category, "Study"
        )

    def test_bills(self):
        self.assertEqual(
            parsers.parse_expense("spent 1200 on electricity bill").category,
            "Bills",
        )

    def test_shopping(self):
        self.assertEqual(
            parsers.parse_expense("spent 300 on shoes").category, "Shopping"
        )

    def test_other(self):
        self.assertEqual(
            parsers.parse_expense("spent 50 on random stuff").category, "Other"
        )

    def test_paid_for_cab(self):
        parsed = parsers.parse_expense("paid 200 for cab")
        self.assertEqual(parsed.category, "Travel")
        self.assertEqual(parsed.note, "cab")

    def test_bought_without_joining_word(self):
        parsed = parsers.parse_expense("bought 300 shoes")
        self.assertEqual(parsed.category, "Shopping")
        self.assertEqual(parsed.note, "shoes")

    def test_amount_only(self):
        parsed = parsers.parse_expense("spent 99")
        self.assertEqual(parsed.amount, 99)
        self.assertEqual(parsed.note, "")

    def test_amount_with_comma(self):
        parsed = parsers.parse_expense("spent 1,200 on rent")
        self.assertEqual(parsed.amount, 1200)
        self.assertEqual(parsed.category, "Bills")
        self.assertEqual(parsed.note, "rent")

    def test_leading_i_is_accepted(self):
        parsed = parsers.parse_expense("I spent 120 on lunch")
        self.assertEqual(parsed.amount, 120)
        self.assertEqual(parsed.category, "Food")
        self.assertTrue(parsers.looks_like_expense("I paid 200 for cab"))

    def test_invalid_expense_asks_a_question(self):
        with self.assertRaises(parsers.ParseError):
            parsers.parse_expense("spent on lunch")

    def test_expense_detection(self):
        self.assertTrue(parsers.looks_like_expense("spent 120 on lunch"))
        self.assertFalse(parsers.looks_like_expense("remind me at 5pm"))


if __name__ == "__main__":
    unittest.main()
