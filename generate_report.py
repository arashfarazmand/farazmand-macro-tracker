import os
import json
import requests
import jdatetime
from datetime import date

API_KEY = os.environ.get("FRED_API_KEY", "")
BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "us10y": "DGS10",
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
    months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
              "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    fa_digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    day_fa = str(jd.day).translate(fa_digits)
    year_fa = str(jd.year).translate(fa_digits)
    return f"{day_fa} {months[jd.month - 1]} {year_fa}"


def main():
    if not API_KEY:
        raise SystemExit("FRED_API_KEY environment variable is not set.")

    # Fetch full recent history for every base series (used for real moving averages)
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

    # ---- Real moving averages, computed from full FRED history (not just our daily log) ----
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

    with open("template.html", "r", encoding="utf-8") as f:
        template = f.read()

    history_json = json.dumps(history, ensure_ascii=False)
    output = template.replace("__HISTORY_JSON__", history_json)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output)

    print(f"index.html generated with {len(history)} days of history and real moving averages.")


if __name__ == "__main__":
    main()
