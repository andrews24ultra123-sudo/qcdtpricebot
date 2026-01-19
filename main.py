import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
import httpx

# ================= CONFIG =================

TOKEN = "8591711650:AAHYMbGwiYxCqZm64tKyWiOgl2moiRUvVWM"
CHAT_ID = -5299275232

TZ = ZoneInfo("Asia/Singapore")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

DAILY_REMINDER = "📝 Ascent, please remember to update QCDT price on the portal."

# Public holiday API (Nager.Date)
HOLIDAY_API_BASE = "https://date.nager.at/api/v3/PublicHolidays"

# ================= HELPERS =================

async def tg_post(method: str, payload: dict, timeout: int = 20):
    """Telegram POST helper with logging for Railway."""
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
        print("TG sendPoll: JSON parse failed")
        return

    if r.status_code == 200 and js.get("ok"):
        mid = js["result"]["message_id"]
        await tg_post(
            "pinChatMessage",
            {"chat_id": CHAT_ID, "message_id": mid, "disable_notification": True},
            timeout=10,
        )

def week_range_monday_to_sunday(d: date):
    monday = d.fromordinal(d.toordinal() - d.weekday())  # Mon=0
    sunday = monday.fromordinal(monday.toordinal() + 6)
    return monday, sunday

def fmt_day(d: date) -> str:
    return d.strftime("%a %d %b %Y")

_holiday_cache = {}  # (year, country_code) -> list[dict]

async def fetch_holidays_for_year(country_code: str, year: int):
    key = (year, country_code)
    if key in _holiday_cache:
        return _holiday_cache[key]
    url = f"{HOLIDAY_API_BASE}/{year}/{country_code}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
    _holiday_cache[key] = data
    return data

async def weekly_holiday_summary_message():
    now = datetime.now(TZ)
    monday, sunday = week_range_monday_to_sunday(now.date())
    years_needed = {monday.year, sunday.year}

    countries = [
        ("Singapore", "SG"),
        ("USA", "US"),
        ("Dubai (UAE)", "AE"),
    ]

    lines = [f"📅 Public Holidays This Week ({fmt_day(monday)} → {fmt_day(sunday)})"]

    for label, code in countries:
        hits = []
        for y in years_needed:
            for h in await fetch_holidays_for_year(code, y):
                hd = date.fromisoformat(h["date"])
                if monday <= hd <= sunday:
                    name = h.get("name") or h.get("localName") or "Holiday"
                    hits.append((hd, name))
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
    print(f"BOOT: TZ={TZ}, CHAT_ID={CHAT_ID}")
    print("BOOT: TOKEN hardcoded")

    fired = set()
    last_date = datetime.now(TZ).date()

    # Startup confirmation
    await send_text(
        f"✅ QCDT bot online at {datetime.now(TZ):%a %d %b %Y %H:%M:%S} (SGT)"
    )
    print("BOOT: startup message sent (attempted)")

    last_tick_minute = None

    while True:
        now = datetime.now(TZ)

        # Log once per minute so logs are visible
        key = (now.date(), now.hour, now.minute)
        if last_tick_minute != key:
            print(f"TICK: {now:%a %d %b %Y %H:%M:%S} SGT")
            last_tick_minute = key

        # Reset daily lock
        if now.date() != last_date:
            fired.clear()
            last_date = now.date()
            print("INFO: new day -> fired cleared")

        wd = now.weekday()  # Mon=0 ... Sun=6
        h, m = now.hour, now.minute

        # Monday 2:45 PM — weekly holiday summary
        if wd == 0 and h == 14 and m == 45 and "MON_HOL_SUMMARY" not in fired:
            print("EVENT: MON_HOL_SUMMARY")
            try:
                await send_text(await weekly_holiday_summary_message())
            except Exception as e:
                print(f"ERROR: holiday summary failed: {type(e).__name__}: {e}")
                await send_text(f"⚠️ Holiday summary failed: {type(e).__name__}")
            fired.add("MON_HOL_SUMMARY")

        # Mon–Fri 2:50 PM — reminder text
        if wd < 5 and h == 14 and m == 50 and "DAILY_REMINDER" not in fired:
            print("EVENT: DAILY_REMINDER")
            await send_text(DAILY_REMINDER)
            fired.add("DAILY_REMINDER")

        # Mon–Fri 3:00 PM — poll (sent + pinned)
        if wd < 5 and h == 15 and m == 0 and "DAILY_POLL" not in fired:
            print("EVENT: DAILY_POLL")
            await send_poll_and_pin(
                "Has QCDT price been updated on portal?",
                ["Yes", "No", "NA - public holiday"],
            )
            fired.add("DAILY_POLL")

        await asyncio.sleep(15)

# ================= ENTRY =================

if __name__ == "__main__":
    asyncio.run(scheduler())
