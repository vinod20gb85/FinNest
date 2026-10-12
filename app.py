import sqlite3
from datetime import datetime


DB_FILE = "db/finance.db"


# -----------------------------
# Database
# -----------------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            category TEXT NOT NULL,
            description TEXT,
            transaction_date TEXT,
            created_at TEXT NOT NULL
        )
    """)

    columns = [
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(transactions)"
        ).fetchall()
    ]

    if "transaction_date" not in columns:
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN transaction_date TEXT"
        )

        conn.execute("""
            UPDATE transactions
            SET transaction_date = substr(created_at, 1, 10)
            WHERE transaction_date IS NULL
        """)

    conn.commit()
    conn.close()


def normalize_category(category):
    if not category:
        return "Other"

    value = category.strip().lower()

    category_map = {
        "grocery": "Groceries",
        "groceries": "Groceries",
        
        "fruit": "Fruits",
		"fruits": "Fruits",

        "transport": "Transportation",
        "transportation": "Transportation",
        "travel": "Transportation",

        "fuel": "Fuel",
        "petrol": "Fuel",
        "diesel": "Fuel",

        "salary": "Salary",
        "wages": "Salary",
        "wage": "Salary",

        "shopping": "Shopping",

        "bill": "Bills",
        "bills": "Bills",

        "medical": "Medical",
        "medicine": "Medical",

        "other": "Other"
    }

    return category_map.get(
        value,
        category.strip().title()
    )

# -----------------------------
# Delete
# -----------------------------
def delete_transaction(transaction_id):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        DELETE FROM transactions WHERE id = ?
    """, (transaction_id,))
    conn.commit()
    conn.close()
    
# -----------------------------
# Transactions
# -----------------------------

def add_transaction(data):
    conn = sqlite3.connect(DB_FILE)

    transaction_date = data.get(
        "transaction_date",
        datetime.now().strftime("%Y-%m-%d")
    )

    conn.execute("""
        INSERT INTO transactions (
            type,
            amount,
            currency,
            category,
            description,
            transaction_date,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["type"],
        data["amount"],
        data.get("currency", "INR"),
        normalize_category(
            data.get("category", "Other")
        ),
        data.get("description", ""),
        transaction_date,
        datetime.now().isoformat(
            timespec="seconds"
        )
    ))

    conn.commit()
    conn.close()


# -----------------------------
# Dashboard Summary
# -----------------------------

def get_transaction_summary():
    today = datetime.now()

    if today.month >= 4:
        fy_start_year = today.year
    else:
        fy_start_year = today.year - 1

    start_date = f"{fy_start_year}-04-01"
    end_date = f"{fy_start_year + 1}-04-01"

    conn = sqlite3.connect(DB_FILE)

    income, expenses = conn.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            )
        FROM transactions
        WHERE transaction_date >= ?
          AND transaction_date < ?
    """, (
        start_date,
        end_date
    )).fetchone()

    conn.close()

    return income, expenses, income - expenses


def get_current_month_summary():
    month = datetime.now().strftime("%Y-%m")

    conn = sqlite3.connect(DB_FILE)

    income, expenses = conn.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            )
        FROM transactions
        WHERE substr(transaction_date, 1, 7) = ?
    """, (month,)).fetchone()

    conn.close()

    return income, expenses, income - expenses


# -----------------------------
# Monthly Report
# -----------------------------

def get_monthly_report(month=None):

    if month is None:
        month = datetime.now().strftime("%Y-%m")

    try:
        report_date = datetime.strptime(
            month,
            "%Y-%m"
        )
    except ValueError:
        return "Invalid month. Please use YYYY-MM."

    month_name = report_date.strftime(
        "%B %Y"
    )

    conn = sqlite3.connect(DB_FILE)

    income, expenses = conn.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            )
        FROM transactions
        WHERE substr(transaction_date, 1, 7) = ?
    """, (month,)).fetchone()

    rows = conn.execute("""
        SELECT
            category,
            SUM(amount)
        FROM transactions
        WHERE type = 'expense'
          AND substr(transaction_date, 1, 7) = ?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    """, (month,)).fetchall()

    conn.close()

    savings = income - expenses

    lines = [
        f"{month_name} Financial Report",
        "",
        f"Income: ₹{income:,.2f}",
        f"Expenses: ₹{expenses:,.2f}",
        f"Savings: ₹{savings:,.2f}"
    ]

    if rows:
        lines.extend([
            "",
            "Spending by category:"
        ])

        for category, amount in rows:
            lines.append(
                f"  {category}: ₹{amount:,.2f}"
            )

    return "\n".join(lines)


# -----------------------------
# Financial Year Report
# -----------------------------

def get_yearly_report(year=None):

    if year is None:
        today = datetime.now()

        if today.month >= 4:
            year = today.year
        else:
            year = today.year - 1

    try:
        year = int(year)

        if year < 2000 or year > 2100:
            raise ValueError

    except (ValueError, TypeError):
        return "Invalid year."

    start_date = f"{year}-04-01"
    end_date = f"{year + 1}-04-01"

    conn = sqlite3.connect(DB_FILE)

    income, expenses = conn.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            )
        FROM transactions
        WHERE transaction_date >= ?
          AND transaction_date < ?
    """, (
        start_date,
        end_date
    )).fetchone()

    rows = conn.execute("""
        SELECT
            category,
            SUM(amount)
        FROM transactions
        WHERE type = 'expense'
          AND transaction_date >= ?
          AND transaction_date < ?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    """, (
        start_date,
        end_date
    )).fetchall()

    conn.close()

    savings = income - expenses

    lines = [
        f"Financial Year {year}-{str(year + 1)[-2:]} Report",
        "",
        f"Period: 1 April {year} to 31 March {year + 1}",
        "",
        f"Income: ₹{income:,.2f}",
        f"Expenses: ₹{expenses:,.2f}",
        f"Savings: ₹{savings:,.2f}"
    ]

    if rows:
        lines.extend([
            "",
            "Spending by category:"
        ])

        for category, amount in rows:
            lines.append(
                f"  {category}: ₹{amount:,.2f}"
            )
    else:
        lines.extend([
            "",
            "No expenses recorded for this financial year."
        ])

    return "\n".join(lines)


# -----------------------------
# Transactions
# -----------------------------

def get_recent_transactions(
    limit=20,
    month=None
):

    conn = sqlite3.connect(DB_FILE)

    if not month:
        month = datetime.now().strftime(
            "%Y-%m"
        )

    current_month = datetime.now().strftime(
        "%Y-%m"
    )

    if month == current_month:

        rows = conn.execute("""
            SELECT
				id,
                transaction_date,
                type,
                amount,
                category,
                description
            FROM transactions
            WHERE substr(transaction_date, 1, 7) = ?
            ORDER BY transaction_date DESC, id DESC
            LIMIT ?
        """, (
            month,
            limit
        )).fetchall()

    else:

        rows = conn.execute("""
            SELECT
				id,
                transaction_date,
                type,
                amount,
                category,
                description
            FROM transactions
            WHERE substr(transaction_date, 1, 7) = ?
            ORDER BY amount DESC,
                     transaction_date DESC,
                     id DESC
            LIMIT ?
        """, (
            month,
            limit
        )).fetchall()

    conn.close()

    return rows


# -----------------------------
# Application startup
# -----------------------------
