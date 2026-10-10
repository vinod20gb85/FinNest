# FinNest — Personal Finance & Wealth Manager

A unified Flask-based personal finance application to manage expenses, income, investments, and subscriptions from one place. FinNest combines three personal finance tools into a single application, with Gmail-powered subscription discovery to help identify recurring payments from email receipts.

## Features

### 1. Finance Tracker
- Track income and expenses.
- View income, expenses, and account balance summaries.
- Generate monthly financial reports.
- Generate yearly reports based on the Indian financial year.
- Organize transactions by category.

### 2. Subscription Manager
- Maintain a list of recurring subscriptions.
- Review subscription amounts, billing cycles, and renewal dates.
- Connect to Gmail using read-only OAuth authorization.
- Scan recent emails for potential subscription and billing information.
- Extract details such as provider, amount, currency, billing cycle, and payment date when available.
- Review detected subscriptions before adding them.
- Warn about possible existing subscriptions to reduce duplicates.

**Privacy and control:** Gmail scanning is intended to identify potential subscriptions for review. Scanning alone should not automatically add subscriptions to the database. Confirm the details before choosing to add a subscription.

### 3. Income & Investment Tracker
- Record and manage income and investment-related transactions.
- Review historical transaction information.
- View income and investment information through a dedicated dashboard.

## Technology Stack

- Python
- Flask
- SQLite
- HTML, CSS, and JavaScript
- Google Gmail API
- Google OAuth 2.0
- `python-dotenv` for environment-variable configuration

## Project Structure

The main application combines the three modules.

```text
FinanceFlask/
├── web_app.py
├── app.py
├── subscription_app.py
├── income_app.py
├── income_routes.py
├── templates/
│   ├── index.html
│   ├── subscriptions.html
│   └── income.html
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```

The exact files and additional directories may differ depending on the current version of the project.

### Main application

`web_app.py` is the central Flask entry point. It integrates the finance application, subscription application, and income-related routes.

### Database files

The modules use SQLite databases for storing application data. Keep personal financial data private, and back up your databases before making changes or deploying a new version.

## Prerequisites

Install the following before running the project:

- Python 3.10 or a compatible version supported by your dependencies.
- pip
- Git
- A Google account, if you want to use Gmail subscription scanning.

Check your installed Python version:

```bash
python3 --version
python3 -m pip --version
```

## Installation and Local Setup

### Step 1: Clone the repository

```bash
git clone https://github.com/vinod20gb85/FinanceFlask.git
cd FinanceFlask
```

### Step 2: Create a virtual environment

Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

If the repository contains `requirements.txt`, install the listed dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The Gmail integration requires the appropriate Google API and OAuth libraries. If they are not already listed in `requirements.txt`, add the dependencies used by the application, such as:

```text
Flask
python-dotenv
google-api-python-client
google-auth
google-auth-httplib2
google-auth-oauthlib
```

Keep `requirements.txt` synchronized with the actual project dependencies.

### Step 4: Create the environment file

Create a file named `.env` in the project root, alongside `web_app.py`.

Example local-development configuration:

```dotenv
# Flask session security
SECRET_KEY=replace-with-a-long-random-secret

# Google OAuth credentials
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5000/api/gmail/oauth2callback

# Local development only
OAUTHLIB_INSECURE_TRANSPORT=1
```

**Important configuration notes:**

- Replace the Google OAuth placeholders with your actual credentials.
- The application must load the environment variables and configure its Flask session secret using the variable names expected by the code.
- `SECRET_KEY` is an example variable name. Confirm that `web_app.py` or the relevant configuration code reads it.
- `OAUTHLIB_INSECURE_TRANSPORT=1` is for local HTTP development only. Do not use it in production.
- Never commit `.env` or share the client secret publicly.

### Step 5: Start the application

From the project root, try:

```bash
python web_app.py
```

If the application is configured to listen on port 5000, open:

- Finance dashboard: http://localhost:5000/
- Subscription manager: http://localhost:5000/subscriptions
- Income & Investment dashboard: http://localhost:5000/income

These URLs assume the routes configured in the application. If the server uses a different host or port, adjust them accordingly.

## Gmail Subscription Scanner Setup

The Gmail integration uses Google OAuth 2.0 to authorize read-only access to Gmail messages. Each user should authorize their own Google account.

### Step 1: Create a Google Cloud project

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project or select an existing project.
3. Open **APIs & Services → Library**.
4. Search for **Gmail API** and enable it.

### Step 2: Configure the OAuth consent screen

1. Open **Google Auth Platform** or the OAuth consent-screen settings.
2. Configure the application's name and required contact details.
3. Select the appropriate audience for your application.
4. If the application is in Testing mode, add your Google account as a test user.
5. Save the configuration.

Google may change the names or locations of these settings in its console.

### Step 3: Configure the Gmail permission

Use the Gmail read-only OAuth scope:

```text
https://www.googleapis.com/auth/gmail.readonly
```

This scope allows the application to read Gmail messages. It does not grant permission to send, delete, or modify emails.

Request only the permissions the application actually needs.

### Step 4: Create OAuth credentials

1. Open **APIs & Services → Credentials** or the equivalent Google Auth Platform credentials page.
2. Create an OAuth client ID.
3. Select **Web application** as the application type.
4. Add the following authorized redirect URI for local development:

```text
http://localhost:5000/api/gmail/oauth2callback
```

5. Save the OAuth client.
6. Copy the client ID and client secret into the `.env` file.

The redirect URI in Google Cloud must match `GOOGLE_REDIRECT_URI` in the application exactly, including the protocol, hostname, port, path, and trailing slash if one is used.

### Step 5: Authorize Gmail

1. Start FinNest.
2. Open the Subscription Manager.
3. Choose the Gmail connect or authorization action.
4. Sign in with the Google account you want to scan.
5. Review the requested permissions and grant access.
6. Return to the application and confirm that Gmail is connected.

If the OAuth consent screen is in Testing mode, only configured test users can authorize the application. Testing-mode refresh tokens can also expire under Google's applicable testing restrictions, so you may need to reconnect.

### Step 6: Scan and review subscriptions

1. Start the Gmail scan.
2. Wait for the scan to finish.
3. Review detected subscription candidates.
4. Verify provider names, amounts, currencies, billing cycles, and renewal dates.
5. Check any existing-subscription warnings.
6. Select **Add Subscription** only for entries you want to save.

Some emails may be skipped if they contain no recognizable billing information or cannot be parsed. Check the application logs and scanner results when unexpected messages are skipped.

## Gmail OAuth and Token Storage

The application may store an OAuth token file such as:

```text
gmail_token.json
```

Treat this file as a credential. Anyone who obtains a valid token may be able to access the authorized Gmail account within the granted scope.

- Keep the token outside public version control.
- Restrict file access to the application user.
- Do not commit token files to GitHub.
- Provide a secure token-storage mechanism before deploying to a shared or production server.
- Revoke the application's access from your Google Account if a token is exposed.

The exact token filename and storage path depend on the implementation.

## Production Deployment

For deployment to a hosted server:

1. Configure all environment variables in the hosting platform's secret or environment-variable settings.
2. Set a strong, unique Flask secret key.
3. Use HTTPS.
4. Update `GOOGLE_REDIRECT_URI` to the public HTTPS callback URL.
5. Add that exact HTTPS URL to the authorized redirect URIs in Google Cloud.
6. Remove `OAUTHLIB_INSECURE_TRANSPORT=1`.
7. Confirm that the hosting environment has all dependencies installed.
8. Ensure database files and token storage persist across application restarts and deployments.
9. Configure appropriate logging without exposing tokens, client secrets, or personal financial data.
10. Back up the databases securely.

Do not assume that local OAuth settings or local file paths will work unchanged in production.

For a public application used by people outside your own testing group, review Google's OAuth verification requirements for the requested Gmail scope.

## Security and Privacy

FinNest handles potentially sensitive financial information and Gmail-derived billing details. Follow these practices:

- Never commit `.env`, `gmail_token.json`, or OAuth secrets.
- Do not publish SQLite database files containing personal transactions or subscriptions.
- Keep a strong, unpredictable Flask secret key.
- Use HTTPS in production.
- Grant only the minimum required Google permissions.
- Require explicit user confirmation before saving detected subscriptions.
- Validate and sanitize user inputs.
- Avoid logging complete email contents or other sensitive financial details.
- Back up databases securely and test database recovery.
- Rotate exposed credentials and revoke exposed OAuth tokens promptly.

A `.gitignore` file should include entries similar to:

```gitignore
.env
.env.*
!.env.example

.venv/
venv/
__pycache__/
*.py[cod]

gmail_token.json
token.json
client_secret*.json

*.db
*.sqlite
*.sqlite3

.pytest_cache/
.coverage
```

Adjust the database exclusions if the project intentionally tracks a sanitized sample database. Never commit a real database containing personal financial information.

If a secret or private database has already been committed to a public repository, adding it to `.gitignore` is not enough. Remove it from version control, rotate or revoke exposed credentials, and clean the Git history where appropriate.

## Troubleshooting

### Gmail scanner reports that authorization is required

- Confirm the Google OAuth credentials are correct.
- Confirm that the `.env` file is loaded.
- Verify the callback URL matches the Google Cloud configuration.
- Complete the Google authorization flow again.

### OAuth error: `Missing code verifier`

The OAuth flow may not be preserving its PKCE code verifier between the authorization request and callback.

- Ensure the Flask session is configured with a persistent secret key.
- Ensure the authorization route stores the verifier in the session.
- Ensure the callback uses the same session and retrieves the verifier.
- Check cookie and HTTPS settings if running behind a reverse proxy.

Do not disable OAuth security checks as a workaround.

### Gmail API returns `invalid_grant`

Possible causes include an expired or revoked refresh token, testing-mode token restrictions, incorrect OAuth configuration, or an authorization mismatch.

Reconnect Gmail and inspect the OAuth configuration and application logs.

### Error: `module 'subscription_app' has no attribute 'scan_gmail_subscriptions'`

This means the running code could not find the expected scanner function in the imported module.

- Confirm the deployed `subscription_app.py` contains the function.
- Confirm that the application imports the intended module.
- Check for circular imports or another file shadowing the module.
- Restart the application after deploying the corrected code.

### Gmail messages are skipped

Not every email containing a payment-related word represents a subscription. Check the scanner's matching rules, message parsing, supported currencies, billing formats, and error logs.

### Application cannot open a database

- Verify the database path and file permissions.
- Confirm the application is running from the expected directory.
- Check whether the deployment platform uses an ephemeral filesystem.
- Back up existing databases before changing paths or initializing tables.

## Development Recommendations

- Add automated tests for each module and shared Flask routes.
- Test Gmail OAuth callbacks and scanner parsing with sanitized sample messages.
- Add clear reporting for scanned, skipped, matched, and failed messages.
- Add database migration support before making schema changes.
- Keep dependency versions reproducible.
- Add CI checks for syntax, tests, and accidental secret exposure.
- Document backup and restore procedures.

## License

Add a `LICENSE` file and specify the project's license before inviting contributions or distributing the application.

## Author

Developed by Vinod Kumar.

## Disclaimer

FinNest is a personal finance management tool. Its reports depend on the accuracy and completeness of entered and imported data. Review transactions and subscription details before relying on them for financial decisions.
