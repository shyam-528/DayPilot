"""SQLite storage for tasks, habits, habit logs, and expenses.

One file, no database server. Every function opens a short-lived connection,
which is more than fast enough for a personal bot and avoids threading issues.
"""

import csv
import io
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import config

DB_PATH = config.DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    title       TEXT NOT NULL,
    remind_at   TEXT,
    recurrence  TEXT NOT NULL DEFAULT 'none'
                CHECK (recurrence IN ('none', 'daily', 'weekly')),
    done        INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_done ON tasks (user_id, done);
CREATE INDEX IF NOT EXISTS idx_tasks_remind_at ON tasks (remind_at);

CREATE TABLE IF NOT EXISTS habits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL COLLATE NOCASE,
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS habit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id    INTEGER NOT NULL,
    log_date    TEXT NOT NULL,
    status      INTEGER NOT NULL CHECK (status IN (0, 1)),
    UNIQUE (habit_id, log_date),
    FOREIGN KEY (habit_id) REFERENCES habits (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL NOT NULL CHECK (amount > 0),
    category    TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    spent_at    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_spent
    ON expenses (user_id, spent_at);
"""


def _utc_now() -> str:
    """Audit timestamp in UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, and always close it."""
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and indexes if they do not exist yet."""
    with _db() as conn:
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------
# Tasks / reminders
# --------------------------------------------------------------------------

def add_task(
    user_id: int,
    title: str,
    remind_at: str | None = None,
    recurrence: str = "none",
) -> int:
    """Add a reminder (with a time) or a plain to-do (remind_at=None)."""
    with _db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (user_id, title, remind_at, recurrence, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, title, remind_at, recurrence, _utc_now()),
        )
        return int(cursor.lastrowid)


def add_todo(user_id: int, title: str) -> int:
    """Add a to-do without a reminder time."""
    return add_task(user_id, title)


def get_task(task_id: int) -> sqlite3.Row | None:
    with _db() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()


def list_open_tasks(user_id: int) -> list[sqlite3.Row]:
    """Timed reminders first (soonest first), then plain to-dos."""
    with _db() as conn:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND done = 0
            ORDER BY (remind_at IS NULL), remind_at, id
            """,
            (user_id,),
        ).fetchall()


def list_open_todos(user_id: int) -> list[sqlite3.Row]:
    with _db() as conn:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND done = 0 AND remind_at IS NULL
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()


def mark_task_done(user_id: int, task_id: int) -> bool:
    with _db() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        return cursor.rowcount > 0


def set_task_remind_at(task_id: int, remind_at: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE tasks SET remind_at = ? WHERE id = ?",
            (remind_at, task_id),
        )


def reminders_between(user_id: int, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    """Timed, unfinished reminders inside [start, end)."""
    with _db() as conn:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND done = 0
              AND remind_at IS NOT NULL
              AND remind_at >= ? AND remind_at < ?
            ORDER BY remind_at
            """,
            (user_id, start_iso, end_iso),
        ).fetchall()


def pending_reminders() -> list[sqlite3.Row]:
    """Every timed task still waiting to fire (used on bot startup)."""
    with _db() as conn:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE done = 0 AND remind_at IS NOT NULL
            ORDER BY remind_at
            """
        ).fetchall()


# --------------------------------------------------------------------------
# Habits
# --------------------------------------------------------------------------

def add_habit(user_id: int, name: str) -> bool:
    """Add a habit. Returns False if it already exists for this user."""
    with _db() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO habits (user_id, name, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, name, _utc_now()),
        )
        return cursor.rowcount > 0


def list_habits(user_id: int, active_only: bool = True) -> list[sqlite3.Row]:
    query = "SELECT * FROM habits WHERE user_id = ?"
    params: list[object] = [user_id]
    if active_only:
        query += " AND active = 1"
    query += " ORDER BY id"

    with _db() as conn:
        return conn.execute(query, params).fetchall()


def get_habit(habit_id: int) -> sqlite3.Row | None:
    with _db() as conn:
        return conn.execute(
            "SELECT * FROM habits WHERE id = ?", (habit_id,)
        ).fetchone()


def pending_habits(user_id: int, log_date: str) -> list[sqlite3.Row]:
    """Active habits with no log entry for the given local date."""
    with _db() as conn:
        return conn.execute(
            """
            SELECT h.*
            FROM habits h
            WHERE h.user_id = ? AND h.active = 1
              AND NOT EXISTS (
                  SELECT 1 FROM habit_logs l
                  WHERE l.habit_id = h.id AND l.log_date = ?
              )
            ORDER BY h.id
            """,
            (user_id, log_date),
        ).fetchall()


def log_habit(habit_id: int, log_date: str, status: int) -> None:
    """Insert or update one habit answer for one date (1 = yes, 0 = no)."""
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO habit_logs (habit_id, log_date, status)
            VALUES (?, ?, ?)
            ON CONFLICT (habit_id, log_date)
            DO UPDATE SET status = excluded.status
            """,
            (habit_id, log_date, status),
        )


def get_habit_logs(habit_id: int) -> list[sqlite3.Row]:
    with _db() as conn:
        return conn.execute(
            """
            SELECT * FROM habit_logs
            WHERE habit_id = ?
            ORDER BY log_date
            """,
            (habit_id,),
        ).fetchall()


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------

def add_expense(
    user_id: int,
    amount: float,
    category: str,
    note: str,
    spent_at: str,
) -> int:
    with _db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO expenses
                (user_id, amount, category, note, spent_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, amount, category, note, spent_at, _utc_now()),
        )
        return int(cursor.lastrowid)


def monthly_summary(user_id: int, month: str) -> list[tuple[str, float]]:
    """Category totals for a 'YYYY-MM' month, largest first."""
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ? AND substr(spent_at, 1, 7) = ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id, month),
        ).fetchall()
        return [(row["category"], float(row["total"])) for row in rows]


def spending_on(user_id: int, local_date: str) -> float:
    """Total spending on a local date ('YYYY-MM-DD')."""
    with _db() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE user_id = ? AND spent_at LIKE ?
            """,
            (user_id, f"{local_date}%"),
        ).fetchone()
        return float(row["total"])


def expense_count(user_id: int) -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["count"])


def expenses_csv(user_id: int) -> str:
    """All expenses as CSV text (date, amount, category, note)."""
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT spent_at, amount, category, note
            FROM expenses
            WHERE user_id = ?
            ORDER BY spent_at
            """,
            (user_id,),
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "amount", "category", "note"])
    for row in rows:
        writer.writerow(
            [row["spent_at"], f"{row['amount']:.2f}", row["category"], row["note"]]
        )
    return output.getvalue()
