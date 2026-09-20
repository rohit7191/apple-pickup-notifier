# Apple Store Pickup Notifier

Check Apple Store pickup availability for selected iPhone part numbers and send Pushover alerts when a model is available nearby. The checker uses Playwright and a persistent browser profile to make requests to Apple's store pages.

## How it works

1. Read the part numbers, ZIP code, and optional Pushover credentials from `.env`.
2. Try Apple's fulfillment endpoints with a saved browser session.
3. If the response is blocked or is not JSON, try refreshing the session, first headlessly and then with a visible browser window.
4. Print availability for each store and send a Pushover message for every available part number.

The script sends an alert on **each run** that finds availability; it does not currently suppress repeat alerts for stock that remains available.

| File or location | Purpose |
| --- | --- |
| `apple_checker_persistent.py` | Checks availability and sends notifications. |
| `apple_phone.sh` | Loads `.env`, runs the checker, and appends to `apple_phone.log`. |
| `.env.example` | Public example configuration. |
| `.env` | Your local configuration; ignored by Git. |
| `.venv/` | Local Python environment; ignored by Git. |
| `~/Documents/Scripts/apple_profile/` | Saved browser session and cookies; outside this repository. |
| `/tmp/apple_*.json` | Latest API responses written by the checker for debugging. |

## Set up

You need Python 3 and Playwright on macOS or Linux. A Pushover account is only needed for push notifications.

From the repository directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
cp .env.example .env
```

Edit `.env` before running. The example contains public US part numbers for iPhone 17 Pro Max, iPhone 18 Pro, and iPhone 18 Pro Max. Keep only the models you want to monitor, enter your ZIP code, and replace the Pushover placeholders if you want alerts. `APPLE_SKU_NAMES` maps part numbers to the names shown in logs and notifications.

| Variable | Purpose |
| --- | --- |
| `APPLE_PART_NUMBERS` | Comma-separated list of part numbers to check. |
| `APPLE_PART_NUMBER` | Single-part alternative when `APPLE_PART_NUMBERS` is unset. |
| `APPLE_SKU_NAMES` | Optional JSON object or `PART=Name;PART=Name` list. |
| `APPLE_ZIP` | ZIP code used for nearby store lookup. |
| `PUSHOVER_USER` and `PUSHOVER_TOKEN` | Optional Pushover credentials. Without both, the checker logs results but skips notifications. |
| `APPLE_MODEL_URL` | Optional Apple product page used when refreshing the browser session. |
| `DEBUG` | Set to `1` for extra log messages; leave empty to disable. |

The example config includes an iPhone 18 Pro product page for session refresh. Change `APPLE_MODEL_URL` if you monitor another product family.

Keep `.env` and the browser profile private. The profile contains session cookies. The checker logs the configured ZIP and part numbers, and its debug JSON files include Apple API responses.

## Run a check

```bash
./apple_phone.sh
tail -f apple_phone.log
```

The wrapper uses paths relative to this repository, so it can run from any working directory. If `.env` or `.venv` is missing, it reports the missing setup and exits.

To run the Python script directly, export the required variables from your shell first and use `.venv/bin/python apple_checker_persistent.py`.

## Schedule checks on macOS

Open your crontab with `crontab -e` and add a line using the **absolute path** to the wrapper. For example, a check every 10 minutes:

```cron
*/10 * * * * /absolute/path/to/apple-pickup-notifier/apple_phone.sh
```

Verify the entry and inspect recent output:

```bash
crontab -l
tail -n 120 /absolute/path/to/apple-pickup-notifier/apple_phone.log
```

Cron will not run missed checks while the Mac is asleep. The wrapper does not install Playwright on every run; install Chromium during setup.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Missing .../.env` | Copy `.env.example` to `.env` and fill in your values. |
| `Missing Python environment` | Create `.venv` and install Playwright as shown above. |
| No Pushover alert | Verify both Pushover values; the checker skips alerts when either is missing. |
| Apple returns HTML or HTTP 541 | The checker tries to refresh its session. Run interactively if a visible browser window is needed, and inspect `apple_phone.log`. |
| Stale browser session | Close any browser using `~/Documents/Scripts/apple_profile/`, then move that directory aside and run a new check. |
| Repeated notifications | The checker currently alerts on each run with availability. Increase the schedule interval or add state tracking. |

Apple's store pages and response format can change, so availability checks may need updates when Apple changes its site.
