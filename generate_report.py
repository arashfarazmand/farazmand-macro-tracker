import os
import json
import time
import requests
import jdatetime
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

API_KEY = os.environ.get("FRED_API_KEY", "")
BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "us10y": "DGS10",
    "us2y": "DGS2",
    "t10yie": "T10YIE",
    "dfii10": "DFII10",
    "dltiit": "DLTIIT",
    "ffr_lower": "DFEDTARL",
    "ffr_upper": "DFEDTARU",
    "iorb": "IORB",
    "effr": "EFFR",
    "cprate": "RIFSPPFAAD90NB",
    "hyoas": "BAMLH0A0HYM2",
    "vix": "VIXCLS",
    "sahm": "SAHMCURRENT",
    "t10y2y": "T10Y2Y",
    "t10y2ym": "T10Y2YM",
}

MA_KEYS = ["us10y", "t10yie", "dfii10", "dltiit", "iorb", "effr",
           "cprate", "hyoas", "vix", "sahm", "t10y2y", "t10y2ym"]

PREV_KEYS = MA_KEYS  # every numeric series that has a "Yesterday" value

# These two FRED series are published once a month. Their MA windows are converted
# to months so that "MA-7 / MA-30 / MA-60 / MA-All" mean the same stretch of time
# (about 7 / 30 / 60 / 180 days) for every row, instead of 7 / 30 / 60 / 180 MONTHS.
MONTHLY_KEYS = {"sahm", "t10y2ym"}

# Wide sanity ranges: only meant to catch garbage (API glitches), never real markets.
VALID_RANGES = {
    "us10y": (0, 20), "t10yie": (-3, 10), "dfii10": (-6, 15), "dltiit": (-6, 15),
    "iorb": (0, 25), "effr": (0, 25), "cprate": (0, 25), "hyoas": (0, 30),
    "vix": (5, 150), "sahm": (-5, 15), "t10y2y": (-6, 6), "t10y2ym": (-6, 6),
    "realRate": (-7, 15), "cpffr": (-5, 5),
}

HISTORY_PATH = "data/history.json"
MARKETS_RAW_PATH = "data/markets_raw.json"

CALENDAR_SERIES = [
    {"key": "nfp",     "name": "NFP (تغییر اشتغال غیرکشاورزی)", "series_id": "PAYEMS",   "kind": "mom_diff", "unit": "هزار نفر"},
    {"key": "unrate",  "name": "نرخ بیکاری",                     "series_id": "UNRATE",   "kind": "level",    "unit": "%"},
    {"key": "cpi_yoy", "name": "CPI (تورم سالانه)",               "series_id": "CPIAUCSL", "kind": "yoy",      "unit": "%"},
    {"key": "ppi_yoy", "name": "PPI (تورم تولیدکننده سالانه)",    "series_id": "PPIACO",   "kind": "yoy",      "unit": "%"},
    {"key": "retail",  "name": "خرده‌فروشی (ماهانه)",            "series_id": "RSXFS",    "kind": "mom_pct",  "unit": "%"},
    {"key": "pce_yoy", "name": "PCE (تورم مصرفی سالانه)",        "series_id": "PCEPI",    "kind": "yoy",      "unit": "%"},
]

ET = ZoneInfo("America/New_York")
IRAN = ZoneInfo("Asia/Tehran")

FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

WEEKDAY_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

RELEASE_RULES = {
    "nfp": ("first_friday",),
    "unrate": ("first_friday",),
    "cpi_yoy": ("day_of_month", 13),
    "ppi_yoy": ("day_of_month", 16),
    "retail": ("day_of_month", 15),
    "pce_yoy": ("last_business_day",),
}

CURRENCY_MAIN = [
    ("usd", "دلار آمریکا", "🇺🇸", ""), ("usdt", "تتر (Tether)", "🟢", ""), ("eur", "یورو", "🇪🇺", ""), ("gbp", "پوند انگلیس", "🇬🇧", ""),
    ("aed", "درهم امارات", "🇦🇪", ""), ("try", "لیر ترکیه", "🇹🇷", ""), ("jpy", "ین ژاپن", "🇯🇵", ""), ("aud", "دلار استرالیا", "🇦🇺", ""),
    ("nzd", "دلار نیوزلند", "🇳🇿", ""), ("cad", "دلار کانادا", "🇨🇦", ""), ("sgd", "دلار سنگاپور", "🇸🇬", ""), ("chf", "فرانک سوئیس", "🇨🇭", ""),
    ("pkr", "روپیه پاکستان", "🇵🇰", ""), ("azn", "منات آذربایجان", "🇦🇿", ""),
]
CURRENCY_OTHER = [
    ("nok", "کرون نروژ", "🇳🇴", ""), ("sek", "کرون سوئد", "🇸🇪", ""), ("dkk", "کرون دانمارک", "🇩🇰", ""), ("kwd", "دینار کویت", "🇰🇼", ""),
    ("omr", "ریال عمان", "🇴🇲", ""), ("rub", "روبل روسیه", "🇷🇺", ""), ("brl", "رئال برزیل", "🇧🇷", ""), ("thb", "بات تایلند", "🇹🇭", ""),
    ("afn", "افغانی", "🇦🇫", ""), ("inr", "روپیه هند", "🇮🇳", ""), ("cny", "یوان چین", "🇨🇳", ""), ("myr", "رینگیت مالزی", "🇲🇾", ""), ("gel", "لاری گرجستان", "🇬🇪", ""),
]
REMITTANCE = [
    ("usd_shakhs", "حواله دلار (شخصی)", "🇺🇸", ""), ("usd_sherkat", "حواله دلار (شرکتی)", "🇺🇸", ""), ("eur_hav", "حواله یورو", "🇪🇺", ""),
    ("gbp_hav", "حواله پوند", "🇬🇧", ""), ("hav_cad_cheque", "حواله دلار کانادا", "🇨🇦", ""), ("aud_hav", "حواله دلار استرالیا", "🇦🇺", ""),
    ("myr_hav", "حواله رینگیت", "🇲🇾", ""), ("cny_hav", "حواله یوان", "🇨🇳", ""), ("try_hav", "حواله لیر", "🇹🇷", ""),
]
CRYPTO = [
    ("btc", "بیت‌کوین", "₿", ""), ("eth", "اتریوم", "Ξ", ""), ("bnb", "بایننس کوین", "🔶", ""), ("doge", "دوج کوین", "🐕", ""),
]
GOLD_COINS = [
    ("usd_xau", "انس جهانی طلا", "🥇", "$"), ("18ayar", "طلای ۱۸ عیار (هر گرم)", "🟡", ""), ("sekkeh", "سکه طرح امامی", "🪙", ""),
    ("bahar", "سکه بهار آزادی", "🪙", ""), ("nim", "نیم سکه", "🪙", ""), ("rob", "ربع سکه", "🪙", ""),
    ("abshodeh", "مثقال طلای آب‌شده", "🟡", ""), ("gerami", "سکه گرمی", "🪙", ""),
]
GOLD_BUBBLE = [
    ("bub_sekkeh", "حباب سکه امامی", "📊", ""), ("bub_bahar", "حباب سکه بهار آزادی", "📊", ""), ("bub_nim", "حباب نیم سکه", "📊", ""),
    ("bub_rob", "حباب ربع سکه", "📊", ""), ("bub_18ayar", "حباب طلای ۱۸ عیار", "📊", ""), ("bub_gerami", "حباب سکه گرمی", "📊", ""),
]

NAVASAN_SLOTS_MIN = [9 * 60, 13 * 60, 17 * 60]


def _fa_num(n):
    return str(n).translate(FA_DIGITS)


def _jalali_dt_label(dt_iran):
    jd = jdatetime.date.fromgregorian(date=dt_iran.date())
    wd = WEEKDAY_FA[dt_iran.weekday()]
    return f"{wd} {_fa_num(jd.day)} {MONTHS_FA[jd.month - 1]} {_fa_num(jd.year)} - ساعت {dt_iran.strftime('%H:%M')}"


def _now_label(now_iran):
    jd = jdatetime.date.fromgregorian(date=now_iran.date())
    return f"{_fa_num(jd.day)} {MONTHS_FA[jd.month - 1]} {_fa_num(jd.year)} - ساعت {now_iran.strftime('%H:%M')}"


def _first_friday(year, month):
    d = datetime(year, month, 1)
    offset = (4 - d.weekday()) % 7
    return d + timedelta(days=offset)


def _nth_day(year, month, day):
    return datetime(year, month, min(day, 28))


def _last_business_day(year, month):
    if month == 12:
        nxt = datetime(year + 1, 1, 1)
    else:
        nxt = datetime(year, month + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _candidates_for_rule(rule, today):
    out = []
    for add_month in (0, 1, 2):
        y, m = today.year, today.month + add_month
        while m > 12:
            m -= 12
            y += 1
        if rule[0] == "first_friday":
            out.append(_first_friday(y, m))
        elif rule[0] == "day_of_month":
            out.append(_nth_day(y, m, rule[1]))
        elif rule[0] == "last_business_day":
            out.append(_last_business_day(y, m))
    return out


def next_release_within(key, today, window_days=30):
    rule = RELEASE_RULES.get(key)
    if not rule:
        return None
    candidates = _candidates_for_rule(rule, today)
    horizon = today.date() + timedelta(days=window_days)
    future = [c for c in candidates if today.date() <= c.date() <= horizon]
    if not future:
        return None
    chosen = min(future)
    dt_et = chosen.replace(hour=8, minute=30, tzinfo=ET)
    dt_iran = dt_et.astimezone(IRAN)
    return _jalali_dt_label(dt_iran)


def build_fomc_upcoming(today, window_days=30):
    out = []
    horizon = today.date() + timedelta(days=window_days)
    for ds in FOMC_DATES_2026:
        d = datetime.strptime(ds, "%Y-%m-%d").date()
        if today.date() <= d <= horizon:
            dt_et = datetime(d.year, d.month, d.day, 14, 0, tzinfo=ET)
            dt_iran = dt_et.astimezone(IRAN)
            out.append({
                "name": "تصمیم نرخ بهره FOMC",
                "period": "-",
                "previous": None,
                "actual": None,
                "unit": "",
                "release": _jalali_dt_label(dt_iran),
            })
    return out


NAVASAN_API_KEY = os.environ.get("NAVASAN_API_KEY", "")
NAVASAN_BASE = "http://api.navasan.tech/latest/"


def fetch_navasan():
    if not NAVASAN_API_KEY:
        return {}
    try:
        r = requests.get(NAVASAN_BASE, params={"api_key": NAVASAN_API_KEY}, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Navasan fetch failed: {e}")
        return {}


def latest_slot_key(now_iran):
    now_min = now_iran.hour * 60 + now_iran.minute
    passed = [s for s in NAVASAN_SLOTS_MIN if s <= now_min]
    if passed:
        return f"{now_iran.date().isoformat()}-{max(passed)}"
    prev_day = now_iran.date() - timedelta(days=1)
    return f"{prev_day.isoformat()}-{max(NAVASAN_SLOTS_MIN)}"


def load_markets_raw():
    if os.path.exists(MARKETS_RAW_PATH):
        with open(MARKETS_RAW_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_markets_raw(data, fetched_at_label, slot_key):
    os.makedirs(os.path.dirname(MARKETS_RAW_PATH), exist_ok=True)
    with open(MARKETS_RAW_PATH, "w", encoding="utf-8") as f:
        json.dump({"data": data, "fetchedAt": fetched_at_label, "slot": slot_key},
                  f, ensure_ascii=False, indent=2)


def get_navasan_snapshot():
    now_iran = datetime.now(IRAN)
    now_label = _now_label(now_iran)

    slot_key = latest_slot_key(now_iran)
    cached = load_markets_raw()
    force = os.environ.get("FORCE_NAVASAN", "").strip().lower() == "true"
    need_fetch = force or cached is None or cached.get("slot") != slot_key

    if need_fetch:
        data = fetch_navasan()
        if data:
            save_markets_raw(data, now_label, slot_key)
            return data, now_label, True

    if cached:
        return cached["data"], cached["fetchedAt"], False
    return {}, None, False


def build_markets(us10y, us2y, navasan_data, navasan_updated_label):
    def nv(key):
        item = navasan_data.get(key)
        if not item:
            return None
        try:
            return float(str(item.get("value")).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def build_group(items):
        return [{"name": label, "value": nv(key), "icon": icon, "unit": unit} for key, label, icon, unit in items]

    return {
        "us10y": us10y,
        "us2y": us2y,
        "navasanAvailable": bool(navasan_data),
        "lastUpdated": navasan_updated_label,
        "currencyMain": build_group(CURRENCY_MAIN),
        "currencyOther": build_group(CURRENCY_OTHER),
        "remittance": build_group(REMITTANCE),
        "crypto": build_group(CRYPTO),
        "goldCoins": build_group(GOLD_COINS),
        "goldBubble": build_group(GOLD_BUBBLE),
    }


def fetch_series(series_id, limit=250):
    """Fetch the latest `limit` observations of a FRED series (oldest first).
    Retries a few times so one transient network error does not kill the whole run."""
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    last_err = None
    for attempt in range(1, 4):
        try:
            r = requests.get(BASE, params=params, timeout=30)
            r.raise_for_status()
            obs = r.json().get("observations", [])
            result = [(o["date"], float(o["value"])) for o in obs if o["value"] not in (".", "", None)]
            result.reverse()
            return result
        except Exception as e:
            last_err = e
            print(f"FRED fetch {series_id} failed (attempt {attempt}/3): {e}")
            time.sleep(2 * attempt)
    raise last_err


def moving_avg(values, n):
    if not values:
        return None
    vals = values[-n:]
    return round(sum(vals) / len(vals), 2)


def window_for(key, n):
    """Number of observations for an n-day moving average of this series."""
    if key in MONTHLY_KEYS:
        return max(1, round(n / 30.4))
    return n


def ma_block(key, vals):
    return {
        "ma7": moving_avg(vals, window_for(key, 7)),
        "ma30": moving_avg(vals, window_for(key, 30)),
        "ma60": moving_avg(vals, window_for(key, 60)),
        "ma180": moving_avg(vals, window_for(key, 180)),
    }


def effective_market_date(now_et):
    """The row's date = today's date in US Eastern time, except that the weekend
    maps back to Friday (US markets are closed, so there is nothing new to record
    and we do not want flat Saturday/Sunday points in the charts)."""
    d = now_et.date()
    if d.weekday() == 5:
        d -= timedelta(days=1)
    elif d.weekday() == 6:
        d -= timedelta(days=2)
    return d.isoformat()


def load_history():
    """Load history.json and self-heal it: remove duplicate gdate rows (the later row
    wins) and sort strictly ascending by date. Repairs corruption from older bugs."""
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not raw:
        return []

    by_date = {}
    for entry in raw:
        gd = entry.get("gdate")
        if gd:
            by_date[gd] = entry  # later occurrence replaces earlier one

    cleaned = [by_date[gd] for gd in sorted(by_date.keys())]

    if cleaned != raw:
        print(f"Repaired history.json: {len(raw)} raw entries -> {len(cleaned)} clean, sorted entries.")
        save_history(cleaned)

    return cleaned


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def assert_history_ok(history):
    dates = [e.get("gdate") for e in history]
    if any(not d for d in dates) or dates != sorted(set(dates)):
        raise SystemExit(f"history ordering is invalid, refusing to publish: {dates[-6:]}")


def validate_entry(e):
    problems = []
    for k, (lo, hi) in VALID_RANGES.items():
        v = e.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            problems.append(f"{k}: missing or NaN ({v!r})")
        elif not (lo <= v <= hi):
            problems.append(f"{k}: {v} is outside the plausible range [{lo}, {hi}]")
    ffr = e.get("ffr")
    if not ffr or ffr == "-":
        problems.append("ffr: missing")
    return problems


def previous_distinct_ffr(history, today_ffr):
    """The FFR target band only changes at FOMC meetings: return the last band that
    differs from today's (or today's band if it has never changed in our log)."""
    for e in reversed(history):
        f = e.get("ffr")
        if f and f != "-" and f != today_ffr:
            return f
    return today_ffr


def gregorian_to_jalali_label(gdate_str):
    y, m, d = [int(x) for x in gdate_str.split("-")]
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return f"{_fa_num(jd.day)} {MONTHS_FA[jd.month - 1]} {_fa_num(jd.year)}"


def month_label(gdate_str):
    y, m, _ = gdate_str.split("-")
    months_en = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return f"{months_en[int(m)-1]} {y}"


def build_calendar():
    today = datetime.now(ET)
    calendar = []
    for spec in CALENDAR_SERIES:
        obs = fetch_series(spec["series_id"], limit=30)
        if len(obs) < 13:
            continue
        entry = {"name": spec["name"], "unit": spec["unit"]}
        if spec["kind"] == "level":
            latest_date, latest_val = obs[-1]
            prev_date, prev_val = obs[-2]
            entry["period"] = month_label(latest_date)
            entry["previous"] = round(prev_val, 2)
            entry["actual"] = round(latest_val, 2)
        elif spec["kind"] == "mom_diff":
            latest_date, latest_val = obs[-1]
            prev_date, prev_val = obs[-2]
            prev2_date, prev2_val = obs[-3]
            entry["period"] = month_label(latest_date)
            entry["previous"] = round(prev_val - prev2_val, 1)
            entry["actual"] = round(latest_val - prev_val, 1)
        elif spec["kind"] == "mom_pct":
            latest_date, latest_val = obs[-1]
            prev_date, prev_val = obs[-2]
            prev2_date, prev2_val = obs[-3]
            entry["period"] = month_label(latest_date)
            entry["previous"] = round((prev_val - prev2_val) / prev2_val * 100, 2)
            entry["actual"] = round((latest_val - prev_val) / prev_val * 100, 2)
        elif spec["kind"] == "yoy":
            latest_date, latest_val = obs[-1]

            def yoy_at(idx):
                target_date = obs[idx][0]
                y, m, d = target_date.split("-")
                target_prev_year = f"{int(y)-1}-{m}-{d}"
                match = [v for dt, v in obs if dt == target_prev_year]
                if not match:
                    match = [v for dt, v in obs if dt[:7] == f"{int(y)-1}-{m}"]
                if not match:
                    return None
                return round((obs[idx][1] - match[0]) / match[0] * 100, 2)

            entry["period"] = month_label(latest_date)
            entry["actual"] = yoy_at(len(obs) - 1)
            entry["previous"] = yoy_at(len(obs) - 2)
        entry["release"] = next_release_within(spec["key"], today) or "-"
        calendar.append(entry)
    calendar.extend(build_fomc_upcoming(today))
    return calendar


def main():
    if not API_KEY:
        raise SystemExit("FRED_API_KEY environment variable is not set.")

    histories = {}
    for key, series_id in SERIES.items():
        histories[key] = fetch_series(series_id)

    if not any(histories.values()):
        raise SystemExit("Could not fetch any data from FRED.")

    # Row date: today's date in US Eastern time (weekend -> Friday). It is never
    # derived from the FRED observations themselves, so it can only move forward.
    today_et = datetime.now(ET)
    latest_date = effective_market_date(today_et)

    # "Today" = the most recent value FRED has published for each series so far.
    values = {k: (histories[k][-1][1] if histories[k] else None) for k in SERIES}

    fetched_at = _now_label(datetime.now(IRAN))

    lo, hi = values["ffr_lower"], values["ffr_upper"]
    entry = {
        "gdate": latest_date,
        "jdate": gregorian_to_jalali_label(latest_date),
        "fetchedAt": fetched_at,
        "us10y": values["us10y"], "t10yie": values["t10yie"], "dfii10": values["dfii10"],
        "dltiit": values["dltiit"],
        "ffr": f"{lo:.2f}-{hi:.2f}" if lo is not None and hi is not None else "-",
        "iorb": values["iorb"], "effr": values["effr"], "cprate": values["cprate"],
        "hyoas": values["hyoas"], "vix": values["vix"], "sahm": values["sahm"],
        "t10y2y": values["t10y2y"], "t10y2ym": values["t10y2ym"],
    }
    entry["realRate"] = round(entry["us10y"] - entry["t10yie"], 2) if entry["us10y"] is not None and entry["t10yie"] is not None else None
    entry["cpffr"] = round(entry["cprate"] - entry["effr"], 2) if entry["cprate"] is not None and entry["effr"] is not None else None

    # "Yesterday" = the previous distinct value FRED itself published for each series
    # (second-to-last observation), NOT the row we stored for the previous calendar
    # day. So a change is never hidden just because "today" is still showing the last
    # print while FRED has not posted a new one yet.
    prev = {}
    for k in PREV_KEYS:
        h = histories[k]
        prev[k] = h[-2][1] if len(h) >= 2 else None
    # Derived rows use the same previous values that are shown for their components,
    # so the table is arithmetically consistent.
    prev["realRate"] = round(prev["us10y"] - prev["t10yie"], 2) if prev.get("us10y") is not None and prev.get("t10yie") is not None else None
    prev["cpffr"] = round(prev["cprate"] - prev["effr"], 2) if prev.get("cprate") is not None and prev.get("effr") is not None else None

    ma = {}
    for key in MA_KEYS:
        ma[key] = ma_block(key, [v for _, v in histories[key]])

    us10y_map = dict(histories["us10y"]); t10yie_map = dict(histories["t10yie"])
    common_dates = sorted(set(us10y_map) & set(t10yie_map))
    rr_vals = [round(us10y_map[d] - t10yie_map[d], 2) for d in common_dates]
    ma["realRate"] = ma_block("realRate", rr_vals)

    cprate_map = dict(histories["cprate"]); effr_map = dict(histories["effr"])
    common2 = sorted(set(cprate_map) & set(effr_map))
    cpffr_vals = [round(cprate_map[d] - effr_map[d], 2) for d in common2]
    ma["cpffr"] = ma_block("cpffr", cpffr_vals)

    entry["ma"] = ma
    entry["prev"] = prev

    history = load_history()
    entry["prev"]["ffr"] = previous_distinct_ffr(history, entry["ffr"])

    problems = validate_entry(entry)
    if problems:
        print("VALIDATION FAILED - today's row was NOT stored. Problems:")
        for p in problems:
            print("  -", p)
        if not history:
            raise SystemExit("No valid history available to publish.")
    elif history and history[-1]["gdate"] == entry["gdate"]:
        history[-1] = entry
        print(f"Updated existing entry for {entry['gdate']}")
    elif history and entry["gdate"] < history[-1]["gdate"]:
        print(f"WARNING: refusing to insert out-of-order date {entry['gdate']} "
              f"before existing last entry {history[-1]['gdate']}. Skipping append.")
    else:
        history.append(entry)
        print(f"Added new entry for {entry['gdate']}")

    assert_history_ok(history)
    save_history(history)

    calendar = build_calendar()

    navasan_data, navasan_updated_label, navasan_fresh = get_navasan_snapshot()
    markets = build_markets(values["us10y"], values.get("us2y"), navasan_data, navasan_updated_label)

    with open("template.html", "r", encoding="utf-8") as f:
        template = f.read()

    output = template.replace("__HISTORY_JSON__", json.dumps(history, ensure_ascii=False))
    output = output.replace("__CALENDAR_JSON__", json.dumps(calendar, ensure_ascii=False))
    output = output.replace("__MARKETS_JSON__", json.dumps(markets, ensure_ascii=False))

    for token in ("__HISTORY_JSON__", "__CALENDAR_JSON__", "__MARKETS_JSON__"):
        if token in output:
            raise SystemExit(f"Template placeholder {token} was not replaced; not publishing.")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output)

    print(f"index.html generated. history={len(history)} days, calendar={len(calendar)} rows, "
          f"navasan={'fresh-fetch' if navasan_fresh else ('cached' if navasan_data else 'unavailable')}.")


if __name__ == "__main__":
    main()
