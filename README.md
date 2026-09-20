# Apple Store Pickup Notifier

Check Apple Store pickup availability for one or more products and send a Pushover notification when stock is found. The checker uses Playwright with a persistent browser profile, which it can refresh when Apple rejects a stale session.

## Setup

Requires Python 3 and a Pushover account for notifications.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
cp .env.example .env
```

Edit `.env` with your Apple part numbers, ZIP code, and Pushover credentials. `APPLE_PART_NUMBERS` is a comma-separated list. To monitor one product, use `APPLE_PART_NUMBER` instead. `APPLE_SKU_NAMES` is optional JSON mapping part numbers to names. Pushover values are optional; checks still run without notifications.

Run the checker:

```bash
./apple_phone.sh
tail -f apple_phone.log
```

For a recurring check on macOS, add a crontab entry with the absolute path to `apple_phone.sh`, such as:

```cron
*/10 * * * * /absolute/path/to/apple-pickup-notifier/apple_phone.sh
```

The browser profile is stored outside the repository at `~/Documents/Scripts/apple_profile`. Keep it private: it contains session cookies. Debug responses are written to `/tmp/apple_*.json`. Neither location belongs in Git. The wrapper keeps its log in the repository, where `.gitignore` excludes it.

Apple's store pages and responses can change, so a reported failure can require a fresh browser session or code update.
