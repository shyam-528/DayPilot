"""Tests for the streak calculation used by /habits."""

import unittest
from datetime import date

from jobs import _current_streak


class StreakTests(unittest.TestCase):
    def test_unbroken_streak_including_today(self):
        today = date(2026, 11, 5)
        statuses = {
            date(2026, 11, 5): 1,
            date(2026, 11, 4): 1,
            date(2026, 11, 3): 1,
            date(2026, 11, 2): 0,
        }
        self.assertEqual(_current_streak(statuses, today), 3)

    def test_today_unanswered_keeps_yesterdays_streak(self):
        today = date(2026, 11, 5)
        statuses = {
            date(2026, 11, 4): 1,
            date(2026, 11, 3): 1,
        }
        self.assertEqual(_current_streak(statuses, today), 2)

    def test_no_logs_means_zero(self):
        self.assertEqual(_current_streak({}, date(2026, 11, 5)), 0)

    def test_a_no_today_resets_streak(self):
        today = date(2026, 11, 5)
        statuses = {
            date(2026, 11, 5): 0,
            date(2026, 11, 4): 1,
        }
        self.assertEqual(_current_streak(statuses, today), 0)


if __name__ == "__main__":
    unittest.main()
