import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
import httpx

# ================= CONFIG =================

TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
CHAT_ID = -5299275232  # target group

TZ = ZoneInfo("Asia/Singapore")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

DAILY_REMINDER = "📝 Ascent, please remember to update QCDT price on the portal."

# Public holiday API
HOLIDAY_API_BASE = "https://date.nager.at/api/v3/PublicHolidays"

# ================= HELPERS =================

async def send_text(text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )

async def send_poll(question, options):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/sendPoll",
            json={
                "chat_id": CHAT_ID,
                "question": question,
                "options": options,
                "is_anonymous": False,
                "allows_multiple_answers": False,
            },
            timeout=20
        )
        if r.status_code == 200 and r.json().get("ok"):
            mid = r.json()["result"]["message_id"]
            await client.post(
                f"{BASE_URL}/pinChatMessage",
                json={
                    "chat_id": CHAT_ID,
                    "message_id": mid,
                    "disable_notification": True
                },
                timeout=10
            )

def week_range_monday_to_sunday(d: date):
    monday = d.fromordinal(d.toordinal() - d.weekday())
    sunday = monday.fromordinal(monday.toordinal() + 6)
    return monday, sunday

def fmt_day(d: date) -> str:
    return d.strftime("%a %d %b %Y")

_holiday_cache = {}

async def fetch_holidays_for_year(country_code: str, year: int):
    key = (year, country_code)
    if key in _holiday_cache:
        return _holiday_cache[key]

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{HOLIDAY_API_BASE}/{year}/{country_code}",
            timeout=20
        )
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
                    hits.append((hd, h.get("name") or h.get("localName")))

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

        wd = now.weekday()   # Mon=0 ... Sun=6
        h, m = now.hour, now.minute

        # Monday 2:45 PM — weekly holiday summary
        if wd == 0 and h == 14 and m == 45 and "MON_HOL_SUMMARY" not in fired:
            try:
                await send_text(await weekly_holiday_summary_message())
            except Exception as e:
                await send_text(f"⚠️ Holiday summary failed: {type(e).__name__}")
            fired.add("MON_HOL_SUMMARY")

        # Mon–Fri 2:50 PM — reminder text
        if wd < 5 and h == 14 and m == 50 and "DAILY_REMINDER" not in fired:
            await send_text(DAILY_REMINDER)
            fired.add("DAILY_REMINDER")

        # Mon–Fri 3:00 PM — poll (always fires)
        if wd < 5 and h == 15 and m == 0 and "DAILY_POLL" not in fired:
            await send_poll(
                "Has QCDT price been updated on portal?",
                ["Yes", "No", "NA - public holiday"]
            )
            fired.add("DAILY_POLL")

        await asyncio.sleep(15)

# ================= ENTRY =================

if __name__ == "__main__":
    asyncio.run(scheduler())
