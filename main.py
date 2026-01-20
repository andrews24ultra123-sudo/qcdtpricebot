import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
import httpx
import json

# ================= CONFIG =================

TOKEN = "8591711650:AAHYMbGwiYxCqZm64tKyWiOgl2moiRUvVWM"
CHAT_ID = -4680966417

TZ = ZoneInfo("Asia/Singapore")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

DAILY_REMINDER = "📝 Ascent, please remember to update QCDT price on the portal."
HOLIDAY_API_BASE = "https://date.nager.at/api/v3/PublicHolidays"

# ================= HELPERS =================

async def tg_post(method: str, payload: dict, timeout: int = 20):
    url = f"{BASE_URL}/{method}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload, timeout=timeout)
            print(f"TG {method}: {r.status_code} {r.text[:300]}")
            return r
        except Exception as e:
            print(f"TG {method} EXCEPTION: {type(e).__name__}: {e}")
            return None

async def send_text(text: str):
    await tg_post("sendMessage", {"chat_id": CHAT_ID, "text": text}, timeout=10)

async def send_poll_and_pin(question: str, options: list[str]):
    r = await tg_post(
        "sendPoll",
        {
            "chat_id": CHAT_ID,
            "question": question,
            "options": options,
            "is_anonymous": False,
            "allows_multiple_answers": False,
        },
        timeout=20,
    )
    if not r:
        return

    try:
        js = r.json()
    except Exception:
        return

    if r.status_code == 200 and js.get("ok"):
        mid = js["result"]["message_id"]
        await tg_post(
            "pinChatMessage",
            {"chat_id": CHAT_ID, "message_id": mid, "disable_notification": True},
            timeout=10,
        )

def week_range_monday_to_sunday(d: date):
    monday = d.fromordinal(d.toordinal() - d.weekday())
    sunday = monday.fromordinal(monday.toordinal() + 6)
    return monday, sunday

def fmt_day(d: date) -> str:
    return d.strftime("%a %d %b %Y")

_holiday_cache = {}

async def fetch_holidays_for_year(country_code: str, year: int) -> list[dict]:
    key = (year, country_code)
    if key in _holiday_cache:
        return _holiday_cache[key]

    url = f"{HOLIDAY_API_BASE}/{year}/{country_code}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, timeout=20)
        except Exception as e:
            print(f"HOLIDAY GET EXCEPTION {country_code} {year}: {e}")
            _holiday_cache[key] = []
            return []

    if r.status_code != 200:
        print(f"HOLIDAY GET non-200 {country_code} {year}: {r.status_code}")
        _holiday_cache[key] = []
        return []

    ctype = (r.headers.get("content-type") or "").lower()
    if "json" not in ctype:
        print(f"HOLIDAY GET non-json {country_code} {year}: {ctype}")
        _holiday_cache[key] = []
        return []

    try:
        data = r.json()
        if not isinstance(data, list):
            data = []
    except json.JSONDecodeError:
        data = []
    except Exception:
        data = []

    _holiday_cache[key] = data
    return data

async def holiday_summary_for_this_week():
    now = datetime.now(TZ)
    monday, sunday = week_range_monday_to_sunday(now.date())
    years_needed = {monday.year, sunday.year}

    countries = [
        ("Singapore", "SG"),
        ("Dubai (UAE)", "AE"),
    ]

    lines = [f"📅 Public Holidays This Week ({fmt_day(monday)} → {fmt_day(sunday)})"]

    for label, code in countries:
        hits = []
        for y in years_needed:
            for h in await fetch_holidays_for_year(code, y):
                try:
                    hd = date.fromisoformat(h["date"])
                except Exception:
                    continue
                if monday <= hd <= sunday:
                    hits.append((hd, h.get("name") or h.get("localName") or "Holiday"))

        hits.sort(key=lambda x: x[0])

        if not hits:
            lines.append(f"\n• {label}: None")
        else:
            lines.append(f"\n• {label}:")
            for hd, name in hits:
                lines.append(f"  - {hd:%a %d %b}: {name}")

    return "\n".join(lines)

# ================= SCHEDULER LOOP =================

async def scheduler():
    print("BOOT: scheduler() starting")
    fired = set()
    last_date = datetime.now(TZ).date()

    await send_text(
        f"✅ QCDT bot online at {datetime.now(TZ):%a %d %b %Y %H:%M:%S} (SGT)"
    )

    while True:
        now = datetime.now(TZ)

        if now.date() != last_date:
            fired.clear()
            last_date = now.date()

        wd = now.weekday()  # Mon=0 ... Sun=6
        h, m = now.hour, now.minute

        # Mon–Fri 4:00 PM — holiday summary (SG + UAE)
        if wd < 5 and h == 16 and m == 0 and "HOL_SUMMARY" not in fired:
            fired.add("HOL_SUMMARY")
            await send_text(await holiday_summary_for_this_week())

        # Mon–Fri 5:30 PM — reminder
        if wd < 5 and h == 17 and m == 30 and "DAILY_REMINDER" not in fired:
            fired.add("DAILY_REMINDER")
            await send_text(DAILY_REMINDER)

        # Mon–Fri 5:45 PM — poll (sent + pinned)
        if wd < 5 and h == 17 and m == 45 and "DAILY_POLL" not in fired:
            fired.add("DAILY_POLL")
            await send_poll_and_pin(
                "Has QCDT price been updated on portal?",
                ["Yes", "No", "NA - SG/UAE public holiday"],
            )

        await asyncio.sleep(15)

# ================= ENTRY =================

if __name__ == "__main__":
    asyncio.run(scheduler())
