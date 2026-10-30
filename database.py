import sqlite3
from datetime import date, timedelta

DB_FILE = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            avatar_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Миграция: добавляем avatar_url если БД уже создана
    try:
        c.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    except sqlite3.OperationalError:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS streaks (
            user_id INTEGER PRIMARY KEY,
            last_login TEXT,
            streak_days INTEGER DEFAULT 0,
            weekly_wins INTEGER DEFAULT 0,
            weekly_played INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS games (
            user_id INTEGER,
            game_id TEXT,
            wins INTEGER DEFAULT 0,
            played INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, game_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            text TEXT,
            amount_b INTEGER DEFAULT 0,
            amount_s INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_user(user_id, username):
    """Базовый upsert, используется из /start"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT balance, score FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        c.execute("INSERT OR IGNORE INTO streaks (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        return 0, 0
    conn.close()
    return row


def get_user_full(user_id):
    """Полный профиль для Mini App (balance, score, стрики, игры, активность)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT username, avatar_url, balance, score
        FROM users WHERE user_id = ?
    """, (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        return None

    c.execute("""
        SELECT streak_days, weekly_wins, weekly_played
        FROM streaks WHERE user_id = ?
    """, (user_id,))
    streak = c.fetchone() or (0, 0, 0)

    c.execute("""
        SELECT game_id, wins, played FROM games WHERE user_id = ?
    """, (user_id,))
    games = {r[0]: {"wins": r[1], "played": r[2]} for r in c.fetchall()}

    c.execute("""
        SELECT type, text, amount_b, amount_s, timestamp
        FROM activity WHERE user_id = ?
        ORDER BY id DESC LIMIT 5
    """, (user_id,))
    activity = [
        {"type": r[0], "text": r[1], "amount_b": r[2], "amount_s": r[3], "timestamp": r[4]}
        for r in c.fetchall()
    ]

    conn.close()
    return {
        "username": user[0],
        "avatar_url": user[1],
        "balance": user[2],
        "score": user[3],
        "streak_days": streak[0],
        "weekly_wins": streak[1],
        "weekly_played": streak[2],
        "games": games,
        "activity": activity,
    }


def save_avatar(user_id, url):
    if not url:
        return
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE users SET avatar_url = ? WHERE user_id = ?", (url, user_id))
    conn.commit()
    conn.close()


def update_balance(user_id, b_change, s_change, activity_type="reward", activity_text=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ?, score = score + ? WHERE user_id = ?",
              (b_change, s_change, user_id))
    if activity_text:
        c.execute("""
            INSERT INTO activity (user_id, type, text, amount_b, amount_s)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, activity_type, activity_text, b_change, s_change))
    conn.commit()
    conn.close()


def update_streak(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT last_login, streak_days FROM streaks WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if row is None:
        c.execute("INSERT INTO streaks (user_id, last_login, streak_days) VALUES (?, ?, 1)",
                  (user_id, today))
        conn.commit()
        conn.close()
        return 1

    last_login, streak = row
    if last_login == today:
        conn.close()
        return streak

    try:
        last = date.fromisoformat(last_login)
        is_consecutive = (date.today() - last).days == 1
    except Exception:
        is_consecutive = False

    new_streak = streak + 1 if is_consecutive else 1
    c.execute("UPDATE streaks SET last_login = ?, streak_days = ? WHERE user_id = ?",
              (today, new_streak, user_id))
    conn.commit()
    conn.close()
    return new_streak


def update_game(user_id, game_id, won):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if won:
        c.execute("""
            INSERT INTO games (user_id, game_id, wins, played) VALUES (?, ?, 1, 1)
            ON CONFLICT(user_id, game_id) DO UPDATE SET
                wins = wins + 1, played = played + 1
        """, (user_id, game_id))
    else:
        c.execute("""
            INSERT INTO games (user_id, game_id, wins, played) VALUES (?, ?, 0, 1)
            ON CONFLICT(user_id, game_id) DO UPDATE SET
                played = played + 1
        """, (user_id, game_id))
    conn.commit()
    conn.close()


def get_top():
    """Для /top в чате"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    return top


def get_top_full():
    """Для Mini App — с аватарками"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT username, avatar_url, score
        FROM users ORDER BY score DESC LIMIT 10
    """)
    top = [{"username": r[0], "avatar_url": r[1], "score": r[2]} for r in c.fetchall()]
    conn.close()
    return top
