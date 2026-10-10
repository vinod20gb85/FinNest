import sqlite3
import os
import re
import base64
import html as html_lib
from datetime import datetime, date, timedelta
from calendar import monthrange
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "subscriptions.db")

BILLING_CYCLES = ("Monthly", "Quarterly", "Half-Yearly", "Yearly")
STATUSES = ("Active", "Paused", "Cancelled")
DEFAULT_CATEGORIES = (
    "Entertainment", "Software", "Cloud", "News", "Music",
    "Video", "Shopping", "Fitness", "Education", "Other"
)


# ============================================================
# Gmail subscription scanner - Web OAuth
# ============================================================
# Gmail integration uses Google OAuth in the browser. The user does not
# need to download or manage a credentials.json file. OAuth client values
# are supplied to the server through environment variables.
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GMAIL_TOKEN_FILE = os.path.join(BASE_DIR, "gmail_token.json")
GOOGLE_CLIENT_ID_ENV = "GOOGLE_CLIENT_ID"
GOOGLE_CLIENT_SECRET_ENV = "GOOGLE_CLIENT_SECRET"


def _google_oauth_config(redirect_uri):
    client_id = os.environ.get(GOOGLE_CLIENT_ID_ENV, "").strip()
    client_secret = os.environ.get(GOOGLE_CLIENT_SECRET_ENV, "").strip()

    if not client_id or not client_secret:
        raise RuntimeError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET on the machine running Flask."
        )

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def gmail_status():
    """Return Gmail integration readiness without starting OAuth."""
    try:
        from googleapiclient.discovery import build  # noqa: F401
        from google_auth_oauthlib.flow import Flow  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
    except ImportError:
        return {
            "available": False,
            "connected": False,
            "reason": "Gmail packages are not installed."
        }

    if not os.environ.get(GOOGLE_CLIENT_ID_ENV) or not os.environ.get(GOOGLE_CLIENT_SECRET_ENV):
        return {
            "available": True,
            "connected": False,
            "reason": "Google OAuth is not configured on the server."
        }

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(
            GMAIL_TOKEN_FILE, GMAIL_SCOPES
        ) if os.path.exists(GMAIL_TOKEN_FILE) else None

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(GMAIL_TOKEN_FILE, "w", encoding="utf-8") as token:
                token.write(creds.to_json())

        return {
            "available": True,
            "connected": bool(creds and creds.valid),
            "reason": None if creds and creds.valid else "Google authorization is required."
        }
    except Exception as exc:
        return {
            "available": True,
            "connected": False,
            "reason": str(exc)
        }


def begin_gmail_oauth(redirect_uri):
    """Create a Google authorization URL for the browser."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise RuntimeError(
            "Gmail support requires google-api-python-client, "
            "google-auth-httplib2 and google-auth-oauthlib."
        ) from exc

    flow = Flow.from_client_config(
        _google_oauth_config(redirect_uri),
        scopes=GMAIL_SCOPES,
    )
    flow.redirect_uri = redirect_uri

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    return {
        "authorization_url": authorization_url,
        "state": state,
        "code_verifier": getattr(flow, "code_verifier", None),
    }


def complete_gmail_oauth(authorization_response, state, redirect_uri, code_verifier=None):
    """Exchange Google's authorization response for and persist Gmail tokens."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise RuntimeError(
            "Gmail support requires google-api-python-client, "
            "google-auth-httplib2 and google-auth-oauthlib."
        ) from exc

    flow = Flow.from_client_config(
        _google_oauth_config(redirect_uri),
        scopes=GMAIL_SCOPES,
        state=state,
    )
    flow.redirect_uri = redirect_uri

    # Google OAuth may use PKCE. The authorization request created a
    # code_verifier which must be restored on the callback flow before
    # exchanging the authorization code for tokens.
    if code_verifier:
        flow.code_verifier = code_verifier

    flow.fetch_token(authorization_response=authorization_response)

    token_json = flow.credentials.to_json()
    with open(GMAIL_TOKEN_FILE, "w", encoding="utf-8") as token:
        token.write(token_json)

    try:
        os.chmod(GMAIL_TOKEN_FILE, 0o600)
    except OSError:
        pass

    if not os.path.isfile(GMAIL_TOKEN_FILE) or os.path.getsize(GMAIL_TOKEN_FILE) == 0:
        raise RuntimeError("Google authorization completed, but gmail_token.json could not be saved.")

    return gmail_status()


def _gmail_service():
    """Create an authenticated Gmail read-only service using the saved OAuth token."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Gmail support requires google-api-python-client, "
            "google-auth-httplib2 and google-auth-oauthlib."
        ) from exc

    if not os.path.exists(GMAIL_TOKEN_FILE):
        raise RuntimeError("Gmail is not connected. Click Scan Gmail and authorize Google access.")

    creds = Credentials.from_authorized_user_file(
        GMAIL_TOKEN_FILE, GMAIL_SCOPES
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(GMAIL_TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    if not creds.valid:
        raise RuntimeError("Gmail authorization has expired. Click Scan Gmail to reconnect.")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def connect_gmail():
    """Backward-compatible status helper; OAuth itself is browser-driven."""
    return gmail_status()



def _decode_gmail_part(part):
    data = part.get("body", {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
        except Exception:
            return ""

    text_parts = []
    for child in part.get("parts", []) or []:
        text_parts.append(_decode_gmail_part(child))
    return "\n".join(x for x in text_parts if x)

def _plain_email_text(raw):
    raw = html_lib.unescape(raw or "")
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</p>|</div>|</tr>|</li>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n[ \t]+", "\n", raw)
    return raw.strip()

def _header(headers, name):
    wanted = name.lower()
    for h in headers or []:
        if h.get("name", "").lower() == wanted:
            return h.get("value", "")
    return ""

def _parse_amount(text):
    patterns = [
        r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:USD|US\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:EUR|€)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            value = float(match.group(1).replace(",", ""))
            currency = "INR" if "₹" in match.group(0) or re.search(r"Rs|INR", match.group(0), re.I) else "USD"
            if "EUR" in match.group(0) or "€" in match.group(0):
                currency = "EUR"
            return value, currency
    return None, "INR"

def _parse_date(text, keywords=None):
    patterns = [
        r"\b(20\d{2}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]20\d{2})\b",
        r"\b([A-Z][a-z]{2,8}\s+\d{1,2},\s+20\d{2})\b",
    ]
    source = text
    if keywords:
        for keyword in keywords:
            m = re.search(keyword + r".{0,100}", text, flags=re.I | re.S)
            if m:
                source = m.group(0)
                break
    for pattern in patterns:
        m = re.search(pattern, source)
        if not m:
            continue
        raw = m.group(1)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
    return None

def _frequency(text):
    if re.search(r"monthly|per month|each month|every month", text, re.I):
        return "Monthly"
    if re.search(r"quarterly|every 3 months", text, re.I):
        return "Quarterly"
    if re.search(r"half[- ]yearly|semi[- ]annual|every 6 months", text, re.I):
        return "Half-Yearly"
    if re.search(r"annual|annually|yearly|per year|every year", text, re.I):
        return "Yearly"
    return "Monthly"

def _category(name, sender, text):
    hay = f"{name} {sender} {text}".lower()
    if any(x in hay for x in ("netflix", "prime video", "disney", "hotstar", "youtube", "spotify", "music")):
        return "Entertainment"
    if any(x in hay for x in ("github", "microsoft 365", "office 365", "adobe", "canva", "notion", "dropbox", "software")):
        return "Software"
    if any(x in hay for x in ("icloud", "google one", "google storage", "onedrive", "cloud")):
        return "Cloud"
    if any(x in hay for x in ("news", "times", "newspaper")):
        return "News"
    if "fitness" in hay or "gym" in hay:
        return "Fitness"
    if "education" in hay or "coursera" in hay or "udemy" in hay:
        return "Education"
    return "Other"

def _provider_name(sender, subject):
    match = re.match(r"\s*(.*?)\s*<([^>]+)>", sender or "")
    display = match.group(1).strip().strip('"') if match else ""
    address = match.group(2) if match else sender
    if display:
        return display
    if address and "@" in address:
        return address.split("@", 1)[0].replace(".", " ").replace("-", " ").title()
    return subject.split(" ", 1)[0] if subject else "Unknown"

def _candidate_from_message(message):
    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    sender = _header(headers, "From")
    subject = _header(headers, "Subject")
    received = _header(headers, "Date")
    body = _plain_email_text(_decode_gmail_part(payload))
    text = f"{subject}\n{body}"[:30000]

    amount, currency = _parse_amount(text)
    next_date = _parse_date(text, [
        r"next payment date", r"next billing date", r"next charge", r"renews? on", r"renewal date", r"renew[s]? on"
    ])
    if not next_date:
        next_date = _parse_date(text)

    frequency = _frequency(text)
    name = _provider_name(sender, subject)
    category = _category(name, sender, text)

    try:
        email_date = parsedate_to_datetime(received).date().isoformat() if received else None
    except Exception:
        email_date = None

    # If the email is a payment/renewal notice but does not state the next
    # billing date, estimate it from the email date and detected billing cycle.
    if not next_date and email_date:
        base = date.fromisoformat(email_date)
        months = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}[frequency]
        target_month = base.month - 1 + months
        year = base.year + target_month // 12
        month = target_month % 12 + 1
        day = min(base.day, monthrange(year, month)[1])
        next_date = date(year, month, day).isoformat()

    # A subscription email should contain at least a billing/payment signal.
    signal = re.search(r"subscription|renew|renewal|billing|bill|invoice|receipt|membership|payment|charged|charge|trial", text, re.I)
    if not signal or amount is None:
        return None

    return {
        "message_id": message.get("id"),
        "thread_id": message.get("threadId"),
        "name": name,
        "amount": round(amount, 2),
        "currency": currency,
        "billing_cycle": frequency,
        "next_payment_date": next_date or date.today().isoformat(),
        "start_date": email_date,
        "category": category,
        "payment_method": "",
        "status": "Active",
        "auto_renew": True,
        "description": f"Detected from Gmail: {subject}" if subject else "Detected from Gmail",
        "email_subject": subject,
        "email_from": sender,
        "email_date": email_date,
        "confidence": "High" if next_date and amount else "Medium",
    }

def scan_gmail_subscriptions(max_results=50, newer_than="180d"):
    """Find likely subscription/renewal emails and return reviewable candidates."""
    service = _gmail_service()
    query = (
        f"newer_than:{newer_than} "
        "{subscription renewal billing invoice receipt membership payment charged charge}"
    )
    response = service.users().messages().list(
        userId="me", q=query, maxResults=max(1, min(int(max_results), 100))
    ).execute()

    existing = list_subscriptions(status="All")
    existing_names = {re.sub(r"[^a-z0-9]", "", x["name"].lower()) for x in existing}
    candidates = []
    seen = set()

    for ref in response.get("messages", []):
        message = service.users().messages().get(
            userId="me", id=ref["id"], format="full"
        ).execute()
        candidate = _candidate_from_message(message)
        if not candidate:
            continue

        key = re.sub(r"[^a-z0-9]", "", candidate["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        candidate["existing_match"] = key in existing_names
        candidates.append(candidate)

    return candidates

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
