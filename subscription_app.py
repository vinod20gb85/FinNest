import sqlite3
import os
from datetime import datetime, date, timedelta
from calendar import monthrange

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "subscriptions.db")

BILLING_CYCLES = ("Monthly", "Quarterly", "Half-Yearly", "Yearly")
STATUSES = ("Active", "Paused", "Cancelled")
DEFAULT_CATEGORIES = (
    "Entertainment", "Software", "Cloud", "News", "Music",
    "Video", "Shopping", "Fitness", "Education", "Other"
)


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            currency TEXT NOT NULL DEFAULT 'INR',
            billing_cycle TEXT NOT NULL,
            next_payment_date TEXT NOT NULL,
            start_date TEXT,
            category TEXT NOT NULL DEFAULT 'Other',
            payment_method TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            auto_renew INTEGER NOT NULL DEFAULT 1,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscription_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            status TEXT NOT NULL DEFAULT 'Paid',
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subscription_id)
                REFERENCES subscriptions(id)
                ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


def _validate_date(value, field_name="date"):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}. Use YYYY-MM-DD.")


def _validate_subscription_data(data):
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Subscription name is required.")

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        raise ValueError("Amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    billing_cycle = str(data.get("billing_cycle", "Monthly")).strip()
    if billing_cycle not in BILLING_CYCLES:
        raise ValueError("Invalid billing cycle.")

    next_payment_date = _validate_date(
        data.get("next_payment_date"), "next payment date"
    )

    start_date_value = data.get("start_date")
    if start_date_value:
        _validate_date(start_date_value, "start date")

    status = str(data.get("status", "Active")).strip()
    if status not in STATUSES:
        raise ValueError("Invalid status.")

    category = str(data.get("category") or "Other").strip() or "Other"
    currency = str(data.get("currency") or "INR").strip().upper() or "INR"
    payment_method = str(data.get("payment_method") or "").strip()
    description = str(data.get("description") or "").strip()

    auto_renew = 1 if data.get("auto_renew", True) in (
        True, 1, "1", "true", "True", "yes", "Yes", "on", "on"
    ) else 0

    return {
        "name": name,
        "amount": amount,
        "currency": currency,
        "billing_cycle": billing_cycle,
        "next_payment_date": next_payment_date.isoformat(),
        "start_date": start_date_value or None,
        "category": category,
        "payment_method": payment_method,
        "status": status,
        "auto_renew": auto_renew,
        "description": description,
    }


def add_subscription(data):
    values = _validate_subscription_data(data)
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO subscriptions (
            name, amount, currency, billing_cycle, next_payment_date,
            start_date, category, payment_method, status, auto_renew,
            description, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        values["name"], values["amount"], values["currency"],
        values["billing_cycle"], values["next_payment_date"],
        values["start_date"], values["category"], values["payment_method"],
        values["status"], values["auto_renew"], values["description"],
        now, now
    ))
    conn.commit()
    subscription_id = cur.lastrowid
    conn.close()
    return get_subscription(subscription_id)


def update_subscription(subscription_id, data):
    try:
        subscription_id = int(subscription_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid subscription ID.")

    values = _validate_subscription_data(data)
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.execute("""
        UPDATE subscriptions
        SET name = ?, amount = ?, currency = ?, billing_cycle = ?,
            next_payment_date = ?, start_date = ?, category = ?,
            payment_method = ?, status = ?, auto_renew = ?,
            description = ?, updated_at = ?
        WHERE id = ?
    """, (
        values["name"], values["amount"], values["currency"],
        values["billing_cycle"], values["next_payment_date"],
        values["start_date"], values["category"], values["payment_method"],
        values["status"], values["auto_renew"], values["description"],
        now, subscription_id
    ))

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("Subscription not found.")

    conn.commit()
    conn.close()
    return get_subscription(subscription_id)


def get_subscription(subscription_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE id = ?",
        (subscription_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_subscriptions(status=None, search=None):
    conn = get_connection()

    sql = "SELECT * FROM subscriptions WHERE 1=1"
    params = []

    if status and status != "All":
        sql += " AND status = ?"
        params.append(status)

    if search:
        sql += """
            AND (
                LOWER(name) LIKE ?
                OR LOWER(category) LIKE ?
                OR LOWER(COALESCE(payment_method, '')) LIKE ?
            )
        """
        term = f"%{search.lower()}%"
        params.extend([term, term, term])

    sql += """
        ORDER BY
            CASE status
                WHEN 'Active' THEN 1
                WHEN 'Paused' THEN 2
                ELSE 3
            END,
            next_payment_date ASC,
            name COLLATE NOCASE ASC
    """

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def set_status(subscription_id, status):
    if status not in STATUSES:
        raise ValueError("Invalid status.")

    conn = get_connection()
    cur = conn.execute("""
        UPDATE subscriptions
        SET status = ?, updated_at = ?
        WHERE id = ?
    """, (
        status,
        datetime.now().isoformat(timespec="seconds"),
        subscription_id
    ))

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("Subscription not found.")

    conn.commit()
    conn.close()
    return get_subscription(subscription_id)


def delete_subscription(subscription_id):
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM subscriptions WHERE id = ?",
        (subscription_id,)
    )

    if cur.rowcount == 0:
        conn.close()
        raise ValueError("Subscription not found.")

    conn.commit()
    conn.close()


def _cycle_months(billing_cycle):
    return {
        "Monthly": 1,
        "Quarterly": 3,
        "Half-Yearly": 6,
        "Yearly": 12,
    }[billing_cycle]


def _add_months(value, months):
    total = value.year * 12 + (value.month - 1) + months
    year = total // 12
    month = total % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def calculate_next_payment(current_date, billing_cycle):
    if billing_cycle not in BILLING_CYCLES:
        raise ValueError("Invalid billing cycle.")
    return _add_months(current_date, _cycle_months(billing_cycle))


def advance_next_payment(subscription_id):
    subscription = get_subscription(subscription_id)
    if not subscription:
        raise ValueError("Subscription not found.")

    current = _validate_date(subscription["next_payment_date"], "next payment date")
    next_date = calculate_next_payment(current, subscription["billing_cycle"])

    conn = get_connection()
    conn.execute("""
        UPDATE subscriptions
        SET next_payment_date = ?, updated_at = ?
        WHERE id = ?
    """, (
        next_date.isoformat(),
        datetime.now().isoformat(timespec="seconds"),
        subscription_id
    ))
    conn.commit()
    conn.close()

    return get_subscription(subscription_id)


def record_payment(subscription_id, payment_date=None, amount=None, notes=""):
    subscription = get_subscription(subscription_id)
    if not subscription:
        raise ValueError("Subscription not found.")

    if payment_date is None:
        payment_date = date.today().isoformat()
    else:
        payment_date = _validate_date(payment_date, "payment date").isoformat()

    if amount is None:
        amount = float(subscription["amount"])

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError("Payment amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    conn = get_connection()
    conn.execute("""
        INSERT INTO subscription_payments (
            subscription_id, payment_date, amount, status, notes, created_at
        )
        VALUES (?, ?, ?, 'Paid', ?, ?)
    """, (
        subscription_id,
        payment_date,
        amount,
        str(notes or "").strip(),
        datetime.now().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()


def get_payment_history(subscription_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM subscription_payments
        WHERE subscription_id = ?
        ORDER BY payment_date DESC, id DESC
    """, (subscription_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _monthly_equivalent(row):
    months = _cycle_months(row["billing_cycle"])
    return float(row["amount"]) / months


def get_summary():
    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM subscriptions
        WHERE status = 'Active'
    """).fetchall()

    conn.close()

    active_count = len(rows)
    monthly_cost = sum(_monthly_equivalent(row) for row in rows)
    yearly_cost = monthly_cost * 12

    today = date.today()
    horizon = today + timedelta(days=30)

    upcoming = []
    for row in rows:
        payment_date = _validate_date(
            row["next_payment_date"], "next payment date"
        )
        if today <= payment_date <= horizon:
            item = dict(row)
            item["days_until"] = (payment_date - today).days
            upcoming.append(item)

    upcoming.sort(key=lambda item: item["next_payment_date"])

    return {
        "active_count": active_count,
        "monthly_cost": round(monthly_cost, 2),
        "yearly_cost": round(yearly_cost, 2),
        "upcoming_30_days_count": len(upcoming),
        "upcoming_30_days_amount": round(
            sum(float(item["amount"]) for item in upcoming), 2
        ),
        "upcoming": upcoming,
    }


def get_upcoming(days=30):
    try:
        days = max(0, int(days))
    except (TypeError, ValueError):
        days = 30

    today = date.today()
    end = today + timedelta(days=days)

    rows = list_subscriptions(status="Active")
    result = []

    for row in rows:
        payment_date = _validate_date(row["next_payment_date"], "next payment date")
        if today <= payment_date <= end:
            item = dict(row)
            item["days_until"] = (payment_date - today).days
            result.append(item)

    return result


def get_category_summary():
    conn = get_connection()
    rows = conn.execute("""
        SELECT category,
               COUNT(*) AS count,
               SUM(
                   CASE billing_cycle
                       WHEN 'Monthly' THEN amount
                       WHEN 'Quarterly' THEN amount / 3.0
                       WHEN 'Half-Yearly' THEN amount / 6.0
                       WHEN 'Yearly' THEN amount / 12.0
                       ELSE amount
                   END
               ) AS monthly_equivalent
        FROM subscriptions
        WHERE status = 'Active'
        GROUP BY category
        ORDER BY monthly_equivalent DESC
    """).fetchall()
    conn.close()

    return [dict(row) for row in rows]


init_db()


if __name__ == "__main__":
    init_db()
    print(f"Subscription database: {DB_FILE}")
    print(f"Subscriptions: {len(list_subscriptions())}")
