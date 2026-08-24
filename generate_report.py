import os
import json
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

HISTORY_PATH = "data/history.json"

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


def _fa_num(n):
    return str(n).translate(FA_DIGITS)


def _jalali_dt_label(dt_iran):
    jd = jdatetime.date.fromgregorian(date=dt_iran.date())
    wd = WEEKDAY_FA[dt_iran.weekday()]
    return f"{wd} {_fa_num(jd.day)} {MONTHS_FA[jd.month - 1]} {_fa_num(jd.year)} - ساعت {dt_iran.strftime('%H:%M')}"


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
    """Fetch latest Iran market rates from Navasan. Returns {} if no key or on failure."""
    if not NAVASAN_API_KEY:
        return {}
    try:
        r = requests.get(NAVASAN_BASE, params={"api_key": NAVASAN_API_KEY}, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Navasan fetch failed: {e}")
        return {}


def build_markets(us10y, us2y, navasan_data):
    def nv(key):
        item = navasan_data.get(key)
        if not item:
            return None
        try:
            return float(str(item.get("value")).replace(",", ""))
        except (TypeError, ValueError):
            return None

    return {
        "us10y": us10y,
        "us2y": us2y,
        "goldOunce": nv("usd_xau"),
        "irUsdFree": nv("usd_sell"),
        "irGold18k": nv("18ayar"),
        "irGold18kBubble": nv("bub_18ayar"),
        "navasanAvailable": bool(navasan_data),
    }


def fetch_series(series_id, limit=250):
    """Fetch the most recent `limit` observations, ascending by date, missing values dropped."""
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    result = [(o["date"], float(o["value"])) for o in obs if o["value"] not in (".", "", None)]
    result.reverse()
    return result


def moving_avg(values, n):
    if not values:
        return None
    vals = values[-n:]
    return round(sum(vals) / len(vals), 2)


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def gregorian_to_jalali_label(gdate_str):
    y, m, d = [int(x) for x in gdate_str.split("-")]
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    day_fa = _fa_num(jd.day)
    year_fa = _fa_num(jd.year)
    return f"{day_fa} {MONTHS_FA[jd.month - 1]} {year_fa}"


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

    values = {k: (histories[k][-1][1] if histories[k] else None) for k in SERIES}
    latest_date = None
    for k in SERIES:
        if histories[k]:
            d = histories[k][-1][0]
            if latest_date is None or d > latest_date:
                latest_date = d

    if latest_date is None:
        raise SystemExit("Could not fetch any data from FRED.")

    entry = {
        "gdate": latest_date,
        "jdate": gregorian_to_jalali_label(latest_date),
        "us10y": values["us10y"],
        "t10yie": values["t10yie"],
        "dfii10": values["dfii10"],
        "dltiit": values["dltiit"],
        "ffr": f'{values["ffr_lower"]:.2f}-{values["ffr_upper"]:.2f}' if values["ffr_lower"] and values["ffr_upper"] else "-",
        "iorb": values["iorb"],
        "effr": values["effr"],
        "cprate": values["cprate"],
        "hyoas": values["hyoas"],
        "vix": values["vix"],
        "sahm": values["sahm"],
        "t10y2y": values["t10y2y"],
        "t10y2ym": values["t10y2ym"],
    }
    entry["realRate"] = round(entry["us10y"] - entry["t10yie"], 2) if entry["us10y"] is not None and entry["t10yie"] is not None else None
    entry["cpffr"] = round(entry["cprate"] - entry["effr"], 2) if entry["cprate"] is not None and entry["effr"] is not None else None

    ma = {}
    for key in MA_KEYS:
        vals = [v for _, v in histories[key]]
        ma[key] = {
            "ma7": moving_avg(vals, 7),
            "ma30": moving_avg(vals, 30),
            "ma60": moving_avg(vals, 60),
            "ma180": moving_avg(vals, 180),
        }

    us10y_map = dict(histories["us10y"])
    t10yie_map = dict(histories["t10yie"])
    common_dates = sorted(set(us10y_map) & set(t10yie_map))
    rr_vals = [round(us10y_map[d] - t10yie_map[d], 2) for d in common_dates]
    ma["realRate"] = {
        "ma7": moving_avg(rr_vals, 7),
        "ma30": moving_avg(rr_vals, 30),
        "ma60": moving_avg(rr_vals, 60),
        "ma180": moving_avg(rr_vals, 180),
    }

    cprate_map = dict(histories["cprate"])
    effr_map = dict(histories["effr"])
    common2 = sorted(set(cprate_map) & set(effr_map))
    cpffr_vals = [round(cprate_map[d] - effr_map[d], 2) for d in common2]
    ma["cpffr"] = {
        "ma7": moving_avg(cpffr_vals, 7),
        "ma30": moving_avg(cpffr_vals, 30),
        "ma60": moving_avg(cpffr_vals, 60),
        "ma180": moving_avg(cpffr_vals, 180),
    }

    entry["ma"] = ma

    history = load_history()

    if history and history[-1]["gdate"] == entry["gdate"]:
        history[-1] = entry
        print(f"Updated existing entry for {entry['gdate']}")
    else:
        history.append(entry)
        print(f"Added new entry for {entry['gdate']}")

    save_history(history)

    calendar = build_calendar()

    navasan_data = fetch_navasan()
    markets = build_markets(values["us10y"], values.get("us2y"), navasan_data)

    with open("template.html", "r", encoding="utf-8") as f:
        template = f.read()

    history_json = json.dumps(history, ensure_ascii=False)
    calendar_json = json.dumps(calendar, ensure_ascii=False)
    markets_json = json.dumps(markets, ensure_ascii=False)
    output = template.replace("__HISTORY_JSON__", history_json)
    output = output.replace("__CALENDAR_JSON__", calendar_json)
    output = output.replace("__MARKETS_JSON__", markets_json)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output)

    print(f"index.html generated with {len(history)} days of history, {len(calendar)} calendar rows, navasan={'ok' if navasan_data else 'skipped'}.")


if __name__ == "__main__":
    main()
