#!/usr/bin/env python3
import os, json, asyncio, sys, pathlib, time, random
from urllib.parse import urlencode
from playwright.async_api import async_playwright, TimeoutError as PwTimeout

# ------------ env ------------
SKU_SINGLE = os.environ.get("APPLE_PART_NUMBER", "").strip()
PARTS_ENV  = os.environ.get("APPLE_PART_NUMBERS", "").strip()
ZIP        = os.environ.get("APPLE_ZIP", "").strip()
PUSER      = os.environ.get("PUSHOVER_USER", "").strip()
PTOK       = os.environ.get("PUSHOVER_TOKEN", "").strip()
DEBUG      = os.environ.get("DEBUG", "").strip()

# Optional: override the model page we open when auto-seeding
MODEL_URL = os.environ.get(
    "APPLE_MODEL_URL",
    "https://www.apple.com/us/shop/buy-iphone/iphone-17-pro"
).strip()

# Friendly names: either JSON like {"PART_NUMBER_1":"First model", ...}
# or "PART_NUMBER_1=First model;PART_NUMBER_2=Second model"
def _parse_sku_names_env():
    raw = os.environ.get("APPLE_SKU_NAMES", "").strip()
    if not raw:
        return {}
    # try JSON first
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            return {str(k).strip(): str(v).strip() for k, v in d.items()}
    except Exception:
        pass
    # fallback to "K=V;K=V" format
    out = {}
    for chunk in raw.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and v:
                out[k] = v
    return out

SKU_NAMES = _parse_sku_names_env()

# Normalize SKUs list
def _parse_skus():
    if PARTS_ENV:
        skus = [s.strip() for s in PARTS_ENV.replace("\n", " ").split(",") if s.strip()]
        if skus:
            return skus
    if SKU_SINGLE:
        return [SKU_SINGLE]
    return []

SKU_LIST = _parse_skus()

# ------------ const ------------
PROFILE_DIR = os.path.expanduser("~/Documents/Scripts/apple_profile")
BUY_IPHONE  = "https://www.apple.com/us/shop/buy-iphone"
FULFILL_A   = "https://www.apple.com/us/shop/fulfillment-messages"
FULFILL_B   = "https://www.apple.com/shop/fulfillment-messages"

UA_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Safari/605.1.15"
)

def pushover(title, message):
    if not (PUSER and PTOK):
        print("Pushover not configured; skipping.")
        return
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode(
        {"token": PTOK, "user": PUSER, "title": title, "message": message}
    ).encode("utf-8")
    try:
        with urllib.request.urlopen(
            urllib.request.Request("https://api.pushover.net/1/messages.json", data=data),
            timeout=15,
        ) as r:
            body = r.read().decode("utf-8", "ignore")
            print("Pushover:", r.getcode(), body)
    except Exception as e:
        print("Pushover failed:", e)

def extract_stores(j):
    b = (j or {}).get("body") or {}
    s = b.get("stores")
    if s: return s
    s = (((b.get("content") or {}).get("pickupMessage") or {}).get("stores")) or []
    return s or []

def is_pickup_available(inf: dict) -> bool:
    disp = (inf.get("pickupDisplay") or "").strip().lower()
    good = {
        "available",
        "available today",
        "available tomorrow",
        "in store pickup available",
        "available for pickup",
        "pickup available",
    }
    if disp in good:
        return True
    if "unavailable" in disp:     # guard against substring trap
        return False
    if inf.get("pickupEligible") is True:
        return True
    return False

# Original single-SKU printer kept for familiarity (not used for notifications anymore)
def parse_hits(j, sku):
    stores = extract_stores(j)
    hits = []
    for s in stores:
        name = s.get("storeName") or s.get("storeNumber") or "Store"
        pa = s.get("partsAvailability") or {}
        info = pa.get(sku)
        cands = [(sku, info)] if info else list(pa.items())
        ok = False
        for part, inf in cands:
            if not inf:
                continue
            if is_pickup_available(inf):
                ok = True
                disp = (inf.get("pickupDisplay") or "")
                hits.append((name, part, disp, bool(inf.get("pickupEligible"))))
                break
        print(f"{name}: {'AVAILABLE' if ok else 'unavailable'}")
    return hits

# Multi-SKU availability map + per-store log (so your terminal output stays useful)
def parse_hits_multi(j, skus):
    stores = extract_stores(j)
    avail = {sku: [] for sku in skus}
    per_store = []
    for s in stores:
        name = s.get("storeName") or s.get("storeNumber") or "Store"
        pa = s.get("partsAvailability") or {}
        marks = []
        for sku in skus:
            inf = pa.get(sku)
            ok = bool(inf) and is_pickup_available(inf)
            marks.append(f"{sku}:{'✔' if ok else '–'}")
            if ok:
                avail[sku].append(name)
        per_store.append(f"{name}: " + " ".join(marks))
    # dedupe + sort store lists
    for sku in avail:
        avail[sku] = sorted(set(avail[sku]))
    return avail, per_store

def params_for(zipc, skus):
    """
    Build Apple params. Supports one or many SKUs:
      parts.0=SKU1, parts.1=SKU2, ...
    """
    p = {
        "pl": "true",
        "mt": "regular",
        "searchNearby": "true",
        "location": zipc,
        "_": str(int(time.time() * 1000))[-6:],  # tiny jitter
    }
    if isinstance(skus, (list, tuple)):
        for i, sku in enumerate(skus):
            p[f"parts.{i}"] = sku
    else:
        p["parts.0"] = str(skus)
    return p

async def fetch_with_context(context, url, params):
    r = await context.request.get(
        url,
        params=params,
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": UA_SAFARI,
            "Referer": BUY_IPHONE,
            "Origin": "https://www.apple.com",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    return r.status, (r.headers.get("content-type", "") or ""), await r.text()

async def page_fetch(page, url, params):
    js = """
    async ({url, params}) => {
      try {
        const u = new URL(url);
        u.search = new URLSearchParams(params).toString();
        const resp = await fetch(u.toString(), {
          method: 'GET',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest'
          },
          credentials: 'include',
          cache: 'no-store'
        });
        const text = await resp.text();
        return { status: resp.status, ct: resp.headers.get('content-type') || '', text };
      } catch (e) {
        return { status: -1, ct: 'error', text: String(e) };
      }
    }
    """
    # NOTE: same two-argument call style you already use
    return await page.evaluate(js, {"url": url, "params": params})

async def try_json_once(ctx, page, url, params, label):
    st, ct, txt = await fetch_with_context(ctx, url, params)
    print(f"[{label} ctx] {st} {ct} {url}?{urlencode(params)}")
    if st == 200 and "application/json" in (ct or "").lower():
        return True, txt
    r = await page_fetch(page, url, params)
    st2, ct2, txt2 = r["status"], (r["ct"] or ""), r["text"]
    print(f"[{label} page] {st2} {ct2} {url}?{urlencode(params)}")
    if st2 == 200 and "application/json" in ct2.lower():
        return True, txt2
    return False, txt if txt else txt2

async def autoseed(page, zipc):
    """
    Attempt to trigger Apple to set antifraud/session bits WITHOUT human clicks.
    (unchanged flow)
    """
    await page.goto(MODEL_URL, wait_until="domcontentloaded", timeout=120_000)
    await page.wait_for_timeout(random.randint(600, 1200))

    candidates = [
        "text=Pick up",
        "text=Pickup",
        "text=Check availability",
        "role=button[name='Check availability']",
        "role=button[name*='Pick up']",
    ]
    for sel in candidates:
        try:
            if sel.startswith("role="):
                await page.get_by_role("button", name="Check availability").click(timeout=1500)
            else:
                await page.locator(sel).first.click(timeout=1500)
            await page.wait_for_timeout(500)
        except Exception:
            pass

    try:
        zip_locators = [
            "input[placeholder*='ZIP']",
            "input[aria-label*='ZIP']",
            "input[name='zip']",
            "input[type='search']",
        ]
        for zsel in zip_locators:
            loc = page.locator(zsel)
            if await loc.count() > 0:
                await loc.first.fill(zipc, timeout=1500)
                await page.wait_for_timeout(250)
                break
    except Exception:
        pass

    for sel in ["text=Search", "text=Update", "role=button[name='Search']"]:
        try:
            if sel.startswith("role="):
                await page.get_by_role("button", name="Search").click(timeout=1200)
            else:
                await page.locator(sel).first.click(timeout=1200)
            await page.wait_for_timeout(800)
            break
        except Exception:
            pass

    await page.wait_for_timeout(random.randint(600, 1200))

async def one_pass(headless: bool, do_seed: bool):
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=headless,
            user_agent=UA_SAFARI,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            page = await ctx.new_page()

            # If requested, try to auto-seed first (unchanged conceptually)
            if do_seed:
                try:
                    await autoseed(page, ZIP)
                except PwTimeout:
                    pass
                except Exception:
                    pass

            # Build multi-SKU params ONCE
            params = params_for(ZIP, SKU_LIST if SKU_LIST else SKU_SINGLE or "")

            # Try both endpoints
            for url in (FULFILL_A, FULFILL_B):
                ok, body = await try_json_once(ctx, page, url, params, label="Fetch")
                if ok:
                    return True, body
            return False, body  # last text (likely HTML)
        finally:
            await ctx.close()

async def run():
    if not SKU_LIST:
        print("ERROR: set APPLE_PART_NUMBERS (comma-separated) or APPLE_PART_NUMBER")
        sys.exit(1)
    if not ZIP:
        print("ERROR: set APPLE_ZIP")
        sys.exit(1)

    print("Starting apple_checker_persistent.py")
    print(f"SKUs = {', '.join(SKU_LIST)}  ZIP = {ZIP}")
    print(f"Profile dir: {PROFILE_DIR}")

    # First: headless, no seeding (fast path for cron)
    ok, body = await one_pass(headless=True, do_seed=False)
    if not ok:
        # Second: headless, try auto-seeding
        ok2, body2 = await one_pass(headless=True, do_seed=True)
        if not ok2:
            # Third: visible + auto-seed (still no human clicks)
            print("No JSON via headless; opening a visible window to auto-seed cookies…")
            ok3, body3 = await one_pass(headless=False, do_seed=True)
            if not ok3:
                print("Auto-seed failed — likely a harder bot wall. Human reseed may be needed.")
                if body3 and ("<html" in body3.lower() or "<!doctype html" in body3.lower()):
                    print("First 200 chars:\n", body3[:200])
                pushover("Apple check: RESEED NEEDED",
                         "Auto-seed failed (541/HTML). Open the window once manually to re-warm cookies.")
                return
            body = body3
        else:
            body = body2

    # Parse JSON
    try:
        data = json.loads(body)
    except Exception:
        print("Bad JSON parse. First 200 chars:\n", body[:200])
        pushover("Apple check failed", "Bad JSON parse.")
        return

    # Save for debugging (keep single-file behavior; last SKU just for filename)
    out = f"/tmp/apple_{(SKU_LIST[-1] if SKU_LIST else SKU_SINGLE).replace('/','_')}_{ZIP}.json"
    try:
        open(out, "wb").write(body.encode("utf-8"))
        if DEBUG: print("Wrote", out)
    except Exception as e:
        if DEBUG: print("Write failed:", e)

    # ---- Availability & notifications (multi-SKU) ----
    availability, per_store = parse_hits_multi(data, SKU_LIST)

    print("\n--- Store results ---")
    for line in per_store:
        print(line)

    any_push = False
    for sku in SKU_LIST:
        stores = availability.get(sku, [])
        pretty = SKU_NAMES.get(sku, sku)
        if stores:
            any_push = True
            msg = f"✅ {pretty} ({sku}) is available near {ZIP}: {', '.join(stores)}"
            print(msg)
            pushover("iPhone Pickup", msg)
        else:
            # Keep quiet for no-availability
            print(f"ℹ️ {pretty} ({sku}) not available near {ZIP} (per API).")

    if not any_push and DEBUG:
        print("[DEBUG] No availability across all SKUs; no push sent.")

def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        pushover("Apple checker crashed", f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    main()
