import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
import httpx
import json

# ================= CONFIG =================

TOKEN = "8591711650:AAHYMbGwiYxCqZm64tKyWiOgl2moiRUvVWM"
CHAT_ID = -4680966417   # UPDATED CHAT ID

TZ = ZoneInfo("Asia/Singapore")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

DAILY_REMINDER = "📝 Ascent, please remember to update QCDT price on the portal."

HOLIDAY_API_BASE = "https://date.nager.at/api/v3/PublicHolidays"

# ================= HELPERS =================

async def tg_post(metho_
