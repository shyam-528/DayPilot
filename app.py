"""DayPilot Local — Streamlit web UI.

Reuses db.py, parsers.py, jobs.py, utils.py, weather.py, config.py.
Run: streamlit run app.py
"""

from __future__ import annotations

import asyncio
import io
from html import escape
from datetime import date, datetime, time as dtime, timedelta

import streamlit as st

import config
import db
import parsers
import utils
import weather

# ---------------------------------------------------------------------------
# Page & style
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DayPilot",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap');
    :root {color-scheme: dark;}
    html, body, [class*="css"], [data-testid="stApp"] {font-family:'DM Sans',sans-serif;}
    [data-testid="stApp"] {
      background: radial-gradient(ellipse 75% 45% at 85% -12%,rgba(109,85,255,.22),transparent 75%),
                  radial-gradient(ellipse 50% 35% at 0% 45%,rgba(30,143,180,.10),transparent 80%),#090d19;
      color:#eef2ff;
    }
    [data-testid="stHeader"] {background:transparent;}
    [data-testid="stToolbar"] {right:1rem;}
    .block-container {max-width:1250px;padding-top:2.1rem;padding-bottom:5rem;}
    h1,h2,h3,h4,[data-testid="stHeading"] {font-family:'Outfit',sans-serif;letter-spacing:-.035em;}
    h3 {color:#f7f8ff!important;}
    p {line-height:1.6;}
    .hero {
      position:relative;overflow:hidden;isolation:isolate;
      border:1px solid rgba(183,183,255,.19);border-radius:26px;
      padding:2.6rem 3rem;margin-bottom:1.65rem;min-height:230px;
      background:linear-gradient(90deg,rgba(25,24,66,.98) 0%,rgba(34,31,90,.91) 48%,rgba(26,23,68,.45) 100%),
        url('https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1600&q=80') center/cover;
      box-shadow:0 24px 70px rgba(0,0,0,.24);
      animation:fadeUp .7s ease both;
    }
    .hero:before {content:'';position:absolute;width:360px;height:360px;border-radius:50%;right:-90px;top:-160px;
      background:radial-gradient(circle,rgba(142,122,255,.45),transparent 70%);z-index:-1;animation:glow 7s ease-in-out infinite alternate;}
    .hero h1 {font-size:clamp(2.3rem,5vw,3.7rem);font-weight:800;margin:.25rem 0 .5rem;color:white;line-height:1.1;}
    .hero p {font-size:1rem;color:#d3d7f7;max-width:540px;margin:.65rem 0 0;}
    .hero .eyebrow {display:inline-block;border:1px solid rgba(208,203,255,.35);border-radius:30px;
      padding:.35rem .8rem;font-size:.72rem;font-weight:800;letter-spacing:.16em;color:#c8c3ff;background:rgba(255,255,255,.06);}
    .hero .orb {position:absolute;right:7%;top:18%;font-size:6.8rem;filter:drop-shadow(0 20px 24px rgba(0,0,0,.28));animation:float 5s ease-in-out infinite;}
    .card {background:linear-gradient(150deg,rgba(28,35,57,.94),rgba(17,23,41,.96));
      border:1px solid rgba(155,170,215,.15);border-radius:20px;padding:1.25rem 1.4rem;margin-bottom:.85rem;
      box-shadow:0 12px 30px rgba(0,0,0,.12);transition:transform .25s ease,border-color .25s ease,box-shadow .25s ease;
      animation:fadeUp .55s ease both;}
    .card:hover {transform:translateY(-3px);border-color:rgba(156,139,255,.48);box-shadow:0 16px 35px rgba(0,0,0,.22);}
    .card h3 {margin:0 0 .55rem;font-family:'DM Sans',sans-serif;font-size:.88rem;font-weight:600;color:#aeb9d6!important;letter-spacing:.01em;}
    .big-number {font-family:'Outfit',sans-serif;font-size:clamp(1.65rem,2.5vw,2.45rem);font-weight:800;margin:.2rem 0;color:#fff;line-height:1.25;overflow-wrap:anywhere;}
    .sub-label {font-size:.78rem;color:#96a3c0;margin:.5rem 0 0;}
    .metric-icon {display:inline-flex;align-items:center;justify-content:center;width:37px;height:37px;
      border-radius:12px;background:rgba(130,112,255,.16);margin-bottom:.65rem;font-size:1.2rem;}
    .tag {display:inline-block;font-size:.72rem;padding:.18rem .6rem;border-radius:99px;margin:.25rem .3rem;
      background:rgba(137,121,255,.16)!important;color:#c7c0ff!important;border:1px solid rgba(137,121,255,.3)!important;}
    .divider {height:1px;background:linear-gradient(90deg,transparent,rgba(157,172,214,.2),transparent);margin:1.55rem 0;border:none;}
    .stButton>button, .stDownloadButton>button, [data-testid="stFormSubmitButton"] button {
      border-radius:12px!important;min-height:43px;font-weight:700!important;transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease!important;
      border-color:rgba(156,169,212,.23);}
    .stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"] button:hover {transform:translateY(-2px);box-shadow:0 8px 20px rgba(92,75,220,.18);}
    button[kind="primary"],button[data-testid="stBaseButton-primary"] {background:linear-gradient(110deg,#7765ff,#a066ed)!important;border:0!important;color:white!important;box-shadow:0 6px 20px rgba(117,93,255,.22);}
    [data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,[data-testid="stTimeInput"] input {
      border-radius:11px!important;background:#111a2c!important;border:1px solid rgba(158,175,219,.2)!important;color:#eef2ff!important;}
    [data-testid="stForm"] {background:rgba(25,32,53,.7);border:1px solid rgba(156,169,212,.15);border-radius:20px;padding:1.2rem;}
    [data-testid="stTabs"] [data-baseweb="tab-list"] {gap:.35rem;background:rgba(23,30,50,.85);padding:.4rem;border-radius:15px;overflow-x:auto;}
    [data-testid="stTabs"] button[role="tab"] {border-radius:10px;padding:.65rem 1.05rem;color:#a9b5d2;white-space:nowrap;font-weight:700;}
    [data-testid="stTabs"] button[aria-selected="true"] {background:rgba(117,101,255,.21);color:#e5e1ff;}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] {display:none;}
    [data-testid="stProgress"] [role="progressbar"]>div {background:linear-gradient(90deg,#7565ff,#50d7ca)!important;}
    [data-testid="stMetric"] {padding:1rem;border-radius:16px;background:rgba(25,32,53,.8);border:1px solid rgba(156,169,212,.15);}
    [data-testid="stAlert"] {border-radius:14px;}
    .section-note {font-size:.86rem;color:#97a4c2;margin:-.25rem 0 1.1rem;}
    .tiny-label {font-size:.73rem;letter-spacing:.13em;text-transform:uppercase;font-weight:800;color:#a59aff;margin-bottom:.3rem;}
    @keyframes fadeUp {from{opacity:0;transform:translateY(13px)}to{opacity:1;transform:translateY(0)}}
    @keyframes float {0%,100%{transform:translateY(0) rotate(-5deg)}50%{transform:translateY(-13px) rotate(5deg)}}
    @keyframes glow {from{opacity:.55;transform:scale(.9)}to{opacity:1;transform:scale(1.2)}}
    @media(max-width:800px){.block-container{padding:1rem .9rem 3rem}.hero{padding:1.8rem 1.4rem;min-height:210px}.hero .orb{font-size:3rem;right:5%;top:12%;opacity:.7}.hero h1{font-size:2.4rem}.card{padding:1rem}.big-number{font-size:1.6rem}}
    @media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}
    </style>
    """,
    unsafe_allow_html=True,
)

USER_ID = config.ALLOWED_USER_ID
TODAY = utils.now_local().date()

# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def init_db_resource() -> None:
    db.init_db()

init_db_resource()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_money(amount: float) -> str:
    return utils.money(amount)

def fmt_when(iso_value: str | None) -> str:
    if not iso_value:
        return "To-do"
    return utils.task_time_label(iso_value)

def add_reminder_from_text(text: str) -> str:
    try:
        parsed = parsers.parse_reminder(text)
    except parsers.ParseError as exc:
        return str(exc)
    task_id = db.add_task(USER_ID, parsed.title, parsed.when.isoformat(), parsed.recurrence)
    if parsed.recurrence == "daily":
        return f"Daily reminder set for {utils.clock(parsed.when)}."
    if parsed.recurrence == "weekly":
        return f"Weekly reminder set for {utils.describe_when(parsed.when)}."
    return f"Reminder set for {utils.describe_when(parsed.when)}."

def add_expense_from_text(text: str) -> str:
    try:
        parsed = parsers.parse_expense(text)
    except parsers.ParseError as exc:
        return str(exc)
    db.add_expense(
        USER_ID,
        parsed.amount,
        parsed.category,
        parsed.note,
        utils.now_local().isoformat(timespec="seconds"),
    )
    return f"Logged: {fmt_money(parsed.amount)}, {parsed.category}."

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="hero">
      <span class="eyebrow">✦ YOUR PERSONAL COMMAND CENTER</span>
      <h1>DayPilot<span style="color:#a99cff">.</span></h1>
      <p>Make space for what matters. Plan your day, build better habits, and stay on top of every expense — all in one place.</p>
      <div class="orb" aria-hidden="true">🚀</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Dashboard metrics
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

open_tasks = db.list_open_tasks(USER_ID)
open_todos = [t for t in open_tasks if t["remind_at"] is None]
open_reminders = [t for t in open_tasks if t["remind_at"] is not None]
expense_count = db.expense_count(USER_ID)
habits = db.list_habits(USER_ID)
pending_habits = db.pending_habits(USER_ID, TODAY.isoformat())

with col1:
    st.markdown(
        f"""
        <div class="card">
            <div class="metric-icon">📋</div><h3>Open Tasks</h3>
            <p class="big-number">{len(open_tasks)}</p>
            <p class="sub-label">{len(open_reminders)} reminders • {len(open_todos)} to-dos</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    today_spend = db.spending_on(USER_ID, TODAY.isoformat())
    st.markdown(
        f"""
        <div class="card">
            <div class="metric-icon">💳</div><h3>Spent Today</h3>
            <p class="big-number">{fmt_money(today_spend)}</p>
            <p class="sub-label">{expense_count} total expenses</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        f"""
        <div class="card">
            <div class="metric-icon">🎯</div><h3>Habits</h3>
            <p class="big-number">{len(habits)}</p>
            <p class="sub-label">{len(pending_habits)} pending today</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    try:
        wt = run_async(weather.get_weather(config.CITY, config.TIMEZONE))
        weather_text = wt or "unavailable"
    except Exception:
        weather_text = "unavailable"
    st.markdown(
        f"""
        <div class="card">
            <div class="metric-icon">☀️</div><h3>Weather — {config.CITY}</h3>
            <p class="big-number">{escape(str(weather_text))}</p>
            <p class="sub-label">{utils.TZ}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Quick add
# ---------------------------------------------------------------------------

st.markdown("### ✨ Quick capture")
st.markdown('<p class="section-note">One thought, one action. Add reminders and expenses using natural language.</p>', unsafe_allow_html=True)
qc1, qc2 = st.columns([4, 1])
with qc1:
    quick_text = st.text_input(
        "Type naturally",
        placeholder="remind me to submit lab record at 5pm  •  spent 120 on lunch",
        label_visibility="collapsed",
    )
with qc2:
    go = st.button("Add", type="primary", use_container_width=True)

if go and quick_text.strip():
    if quick_text.lower().startswith("remind"):
        msg = add_reminder_from_text(quick_text)
    elif parsers.looks_like_expense(quick_text):
        msg = add_expense_from_text(quick_text)
    else:
        msg = "Try: 'remind me to ... at 5pm' or 'spent 120 on lunch'."
    st.info(msg)

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_tasks, tab_expenses, tab_habits, tab_briefing = st.tabs(
    ["📋 Tasks & Reminders", "💸 Expenses", "🎯 Habits", "☀️ Briefing"]
)

# ===========================================================================
# TASKS TAB
# ===========================================================================

with tab_tasks:
    tc1, tc2 = st.columns([3, 2])

    with tc2:
        st.markdown("#### ✨ Create a task")
        with st.form("add_task_form", clear_on_submit=True):
            title = st.text_input("What to do?", placeholder="submit lab record")
            c1, c2 = st.columns(2)
            with c1:
                has_time = st.checkbox("Set a time", value=False)
            with c2:
                repeat = st.selectbox("Repeat", ["none", "daily", "weekly"], index=0)
            remind_at = None
            if has_time:
                d = st.date_input("Date", value=TODAY)
                t = st.time_input("Time", value=dtime(17, 0))
                remind_at = datetime.combine(d, t, tzinfo=utils.TZ).isoformat()
            submitted = st.form_submit_button("Create", use_container_width=True, type="primary")
            if submitted and title.strip():
                db.add_task(USER_ID, title.strip(), remind_at, repeat)
                st.success("Created.")
                st.rerun()

    with tc1:
        st.markdown("#### 📋 Your tasks")
        if not open_tasks:
            st.markdown(
                '<div class="card"><p style="opacity:0.6;margin:0;">No open tasks. Add one above.</p></div>',
                unsafe_allow_html=True,
            )
        else:
            for task in open_tasks:
                is_reminder = task["remind_at"] is not None
                badge = (
                    f'<span class="tag" style="background:#e0e7ff;color:#4338ca;border-color:#c7d2fe;">{task["recurrence"]}</span>'
                    if is_reminder and task["recurrence"] != "none"
                    else ""
                )
                time_label = fmt_when(task["remind_at"])
                with st.container():
                    st.markdown(
                        f"""
                        <div class="card" style="display:flex;align-items:center;justify-content:space-between;">
                            <div>
                                <div style="font-weight:600;">#{task["id"]} {escape(str(task["title"]))}</div>
                                <div style="opacity:0.7;font-size:0.85rem;">
                                    {time_label} {badge}
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    col_a, col_b, col_c = st.columns([1, 1, 6])
                    with col_a:
                        if st.button("✅ Done", key=f"done_{task['id']}", use_container_width=True):
                            db.mark_task_done(USER_ID, task["id"])
                            st.rerun()
                    with col_b:
                        if st.button("✏️", key=f"edit_{task['id']}", help="Edit time", use_container_width=True):
                            st.session_state[f"editing_{task['id']}"] = True
                    with col_c:
                        st.write("")
                    if st.session_state.get(f"editing_{task['id']}"):
                        with st.form(f"edit_form_{task['id']}", clear_on_submit=True):
                            nd = st.date_input("Date", value=TODAY, key=f"ed_d_{task['id']}")
                            nt = st.time_input("Time", value=dtime(17, 0), key=f"ed_t_{task['id']}")
                            nrepeat = st.selectbox("Repeat", ["none", "daily", "weekly"], index=["none","daily","weekly"].index(task["recurrence"]), key=f"ed_r_{task['id']}")
                            c_save, c_cancel = st.columns(2)
                            with c_save:
                                if st.form_submit_button("Save", use_container_width=True, type="primary"):
                                    db.set_task_remind_at(
                                        task["id"],
                                        datetime.combine(nd, nt, tzinfo=utils.TZ).isoformat(),
                                    )
                                    # Note: recurrence change not stored via existing helper; keep simple
                                    st.session_state[f"editing_{task['id']}"] = False
                                    st.rerun()
                            with c_cancel:
                                if st.form_submit_button("Cancel", use_container_width=True):
                                    st.session_state[f"editing_{task['id']}"] = False
                                    st.rerun()

# ===========================================================================
# EXPENSES TAB
# ===========================================================================

with tab_expenses:
    ec1, ec2 = st.columns([2, 3])

    with ec1:
        st.markdown("#### 💳 Log an expense")
        with st.form("add_expense_form", clear_on_submit=True):
            amount = st.number_input("Amount (₹)", min_value=0.01, step=1.0, format="%.2f")
            note = st.text_input("Note / category", placeholder="lunch, bus fare, notebook")
            submitted = st.form_submit_button("Log", use_container_width=True, type="primary")
            if submitted and note.strip():
                cat = parsers.categorize(note)
                db.add_expense(
                    USER_ID,
                    float(amount),
                    cat,
                    note.strip(),
                    utils.now_local().isoformat(timespec="seconds"),
                )
                st.success(f"Logged {fmt_money(amount)} — {cat}.")
                st.rerun()

    with ec2:
        st.markdown("#### 🧾 Recent activity")
        with db._db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM expenses WHERE user_id = ?
                ORDER BY spent_at DESC LIMIT 20
                """,
                (USER_ID,),
            ).fetchall()
        if not rows:
            st.markdown(
                '<div class="card"><p style="opacity:0.6;margin:0;">No expenses yet.</p></div>',
                unsafe_allow_html=True,
            )
        else:
            for row in rows:
                spent_local = datetime.fromisoformat(row["spent_at"]).astimezone(utils.TZ)
                with st.container():
                    st.markdown(
                        f"""
                        <div class="card" style="display:flex;align-items:center;justify-content:space-between;">
                            <div>
                                <div style="font-weight:600;">{escape(str(row["category"]))} — {escape(str(row["note"] or "—"))}</div>
                                <div style="opacity:0.7;font-size:0.85rem;">
                                    {spent_local.strftime('%a %d %b, %I:%M %p')}
                                </div>
                            </div>
                            <div style="font-weight:700;text-align:right;">{fmt_money(row["amount"])}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.markdown("#### 📊 Monthly insights")
    rc1, rc2, rc3 = st.columns([2, 1, 1])
    with rc1:
        month_pick = st.date_input("Month", value=TODAY)
        month_str = month_pick.strftime("%Y-%m")
    with rc2:
        summary = db.monthly_summary(USER_ID, month_str)
        total = sum(a for _, a in summary)
        st.metric(f"Total {month_str}", fmt_money(total))
    with rc3:
        if summary:
            csv_text = db.expenses_csv(USER_ID)
            st.download_button(
                "Export CSV",
                data=csv_text,
                file_name=f"daypilot_expenses_{month_str}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    if summary:
        for cat, amt in summary:
            st.progress(amt / total if total else 0, text=f"{cat}: {fmt_money(amt)}")
    else:
        st.info(f"No expenses for {month_str} yet.")

# ===========================================================================
# HABITS TAB
# ===========================================================================

with tab_habits:
    hc1, hc2 = st.columns([2, 3])

    with hc1:
        st.markdown("#### 🌱 Build a habit")
        with st.form("add_habit_form", clear_on_submit=True):
            hname = st.text_input("Habit name", placeholder="exercise, reading, meditation")
            submitted = st.form_submit_button("Add", use_container_width=True, type="primary")
            if submitted and hname.strip():
                if db.add_habit(USER_ID, hname.strip()):
                    st.success(f"Habit '{hname.strip()}' added.")
                    st.rerun()
                else:
                    st.warning("That habit already exists.")

    with hc2:
        st.markdown("#### 🎯 Today’s check-in")
        if not habits:
            st.markdown(
                '<div class="card"><p style="opacity:0.6;margin:0;">No habits yet. Add one above.</p></div>',
                unsafe_allow_html=True,
            )
        elif not pending_habits:
            st.success("All habits logged for today! 🎉")
        else:
            for habit in pending_habits:
                with st.container():
                    st.markdown(
                        f"""
                        <div class="card" style="display:flex;align-items:center;justify-content:space-between;">
                            <div style="font-weight:600;">Did you {escape(str(habit["name"]))} today?</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Yes", key=f"hy_{habit['id']}", use_container_width=True):
                            db.log_habit(habit["id"], TODAY.isoformat(), 1)
                            st.rerun()
                    with b2:
                        if st.button("❌ No", key=f"hn_{habit['id']}", use_container_width=True):
                            db.log_habit(habit["id"], TODAY.isoformat(), 0)
                            st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.markdown("#### 🔥 Your last 7 days")
    summary_text = jobs.habit_summary_text(USER_ID) if False else None
    # Build summary inline to avoid importing jobs (which needs telegram)
    if habits:
        week_start = TODAY - timedelta(days=6)
        lines = ["Habit summary (last 7 days):"]
        for habit in habits:
            logs = db.get_habit_logs(habit["id"])
            statuses = {
                date.fromisoformat(row["log_date"]): row["status"] for row in logs
            }
            done = sum(
                1 for offset in range(7)
                if statuses.get(week_start + timedelta(days=offset)) == 1
            )
            # streak
            day = TODAY
            if day not in statuses:
                day -= timedelta(days=1)
            streak = 0
            while statuses.get(day) == 1:
                streak += 1
                day -= timedelta(days=1)
            lines.append(f"- {habit['name']}: {done}/7, streak {streak} day{'s' if streak != 1 else ''}")
        for line in lines:
            st.markdown(f'<div class="card"><p style="margin:0.2rem 0;">{line}</p></div>', unsafe_allow_html=True)
    else:
        st.info("No habits yet.")

# ===========================================================================
# BRIEFING TAB
# ===========================================================================

with tab_briefing:
    st.markdown("#### ☀️ Your daily briefing")
    st.markdown('<p class="section-note">A clear snapshot of your day, whenever you need it.</p>', unsafe_allow_html=True)
    if st.button("Generate Briefing Now", type="primary", use_container_width=True):
        st.session_state["show_briefing"] = True
    if st.session_state.get("show_briefing"):
        now = utils.now_local()
        day_start = datetime.combine(TODAY, dtime.min, tzinfo=utils.TZ)
        day_end = day_start + timedelta(days=1)
        reminders = db.reminders_between(USER_ID, day_start.isoformat(), day_end.isoformat())
        todos = db.list_open_todos(USER_ID)
        pending = db.pending_habits(USER_ID, TODAY.isoformat())
        yesterday = TODAY - timedelta(days=1)
        yesterday_total = db.spending_on(USER_ID, yesterday.isoformat())

        wt = run_async(weather.get_weather(config.CITY, config.TIMEZONE))

        st.markdown(
            f"""
            <div class="card">
                <h3>Good morning! {now.strftime('%A, %d %b %Y')}</h3>
                <p><b>Weather in {config.CITY}:</b> {escape(str(wt or 'unavailable right now'))}</p>
                <p><b>Yesterday's spending:</b> {fmt_money(yesterday_total)}</p>
                <hr style="border:none;border-top:1px solid rgba(49,51,63,0.12);margin:1rem 0;">
                <p><b>Today's reminders:</b></p>
                {"".join(f"<p>• {utils.clock(datetime.fromisoformat(t['remind_at']))} - {escape(str(t['title']))}</p>" for t in reminders) if reminders else "<p style='opacity:0.6;'>None</p>"}
                <p><b>To-dos:</b></p>
                {"".join(f"<p>• {escape(str(t['title']))}</p>" for t in todos) if todos else "<p style='opacity:0.6;'>None</p>"}
                <p><b>Habits pending today:</b> {escape(', '.join(h['name'] for h in pending) or 'None')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
