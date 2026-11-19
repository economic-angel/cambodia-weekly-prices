"""Weekly update for the Cambodia farm price dashboard.

Fetches daily prices from CAMAGRIMARKET / AMIS (amis.maff.gov.kh), builds
weekly averages (last 13 complete weeks, with the same week last year and a
5-year normal) and monthly averages, writes data/*.json and rebuilds
index.html from site/template.html.

Run: python scripts/update.py            (anchor = last complete week)
     python scripts/update.py 2026-11-16 (anchor = week starting that Monday)
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request

BASE = "https://amis.maff.gov.kh"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS = [("2", "채소"), ("6", "과일"), ("7", "기타작물"), ("1", "곡물·두류")]
SERIES = [("WP", "도매"), ("RP", "소매")]
WEEKS = 13
KO = {'20002': '여주', '20003': '양배추', '20005': '오이', '20008': '상추', '20010': '토마토', '20011': '롱빈(줄콩)', '20017': '카사바(생)', '20021': '카사바(건조)', '20030': '풋파파야', '20031': '레몬그라스', '60009': '아보카도', '60011': '패션프루트', '60012': '사워솝', '15016': '고무(캄퐁참)', '15014': '건조고무(캄퐁참)', '12002': '쌀(혼합)', '12003': '쌀(낭민)', '12004': '쌀(프카 칸헤이)', '12005': '쌀(센크롭)', '12007': '쌀(IR)', '12010': '쌀(낭콘)', '12012': '찹쌀(백)', '12017': '쌀(프카 롬두올)', '12018': '쌀(센 피도르)', '12019': '쌀(프카 믈리스)', '14001': '흑후추 1등급', '14002': '캐슈넛', '14003': '땅콩', '14005': '녹두', '14006': '참깨(백)', '14008': '대두', '14009': '옥수수(백)', '14013': '캐슈넛(가공)', '11021': '벼 IR(생벼)', '11022': '벼 OM5451(생벼)', '11025': '벼 센크롭(생벼)', '11023': '벼 프카 롬두올(생벼)', '11024': '벼 크롭(생벼)', '11026': '벼 스라응에(생벼)', '11028': '벼 낭암(생벼)', '11030': '벼 참페이사르70(생벼)', '11031': '벼 크롭01(생벼)', '14016': '옥수수 이삭(생)', '14018': '옥수수 알곡(생)', '14020': '캄폿 흑후추(N3)'}
KM_DIGITS = "០១២៣៤៥៦៧៨៩"
KM_MONTHS = ['មករា', 'កុម្ភៈ', 'មីនា', 'មេសា', 'ឧសភា', 'មិថុនា', 'កក្កដា', 'សីហា', 'កញ្ញា', 'តុលា', 'វិច្ឆិកា', 'ធ្នូ']
EN_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def get(path, tries=4):
    url = BASE + path
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (price-dashboard weekly update)", "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network hiccups: retry with backoff
            if i == tries - 1:
                raise RuntimeError(f"AMIS request failed: {path}: {e}")
            time.sleep(3 * (i + 1))


def jround(x):  # JavaScript Math.round for positive numbers
    return int(math.floor(x + 0.5))


def iso_key(d):
    y, w, _ = d.isocalendar()
    return (y, w)


def week_label(monday):
    return f"{monday.month}월 {(monday.day - 1) // 7 + 1}주"


# Thresholds for the weekly data check
WOW_ALERT = 30.0      # % change from the previous week
NORMAL_ALERT = 50.0   # % gap from the 5-year normal
DAILY_FACTOR = 3.0    # a daily price above 3x or below 1/3 of the median of the 8 weeks before


def pct(a, b):
    return None if a is None or b in (None, 0) else round((a / b - 1) * 100, 1)


def build_report(weekly, weeks, daily_recent, invalid, no_data, anchor):
    """Lists values worth a second look in the latest complete week."""
    latest, prev = weeks[-1].isoformat(), weeks[-2].isoformat()
    rows = {}
    for r in weekly:
        rows.setdefault(r["key"], {})[r["week"]] = r
    issues = {"missing": [], "spike": [], "normal_gap": [], "daily_outlier": [], "invalid": [], "inversion": [], "single_day": []}
    for key, wk in rows.items():
        c, p = wk.get(latest), wk.get(prev)
        if c is None:
            continue
        name = f"{c['item']} ({c['type']})"
        if c["price"] is None:
            last = max((w for w, r in wk.items() if r["price"] is not None), default=None)
            issues["missing"].append({"item": name, "last_priced_week": last, "last_price": wk[last]["price"] if last else None})
            continue
        if c["days"] == 1:
            issues["single_day"].append(name)
        ch = pct(c["price"], p["price"] if p else None)
        if ch is not None and abs(ch) >= WOW_ALERT:
            issues["spike"].append({"item": name, "prev": p["price"], "cur": c["price"], "change": ch, "days": c["days"]})
        g = pct(c["price"], c["normal"])
        if g is not None and abs(g) >= NORMAL_ALERT:
            issues["normal_gap"].append({"item": name, "cur": c["price"], "normal": c["normal"], "gap": g})
        vals = daily_recent.get(key, [])
        base = sorted(v for d, v in vals if d < anchor)
        if len(base) >= 4:
            med = base[len(base) // 2]
            for d, v in vals:
                if d >= anchor and (v > med * DAILY_FACTOR or v < med / DAILY_FACTOR):
                    issues["daily_outlier"].append({"item": name, "date": d.isoformat(), "price": jround(v), "median_8w": jround(med)})
    for key, bad in invalid.items():
        code, t = key.split("|")
        name = f"{KO.get(code, code)} ({t})"
        for d, v in bad:
            issues["invalid"].append({"item": name, "date": d, "value": v})
    for key, wk in rows.items():
        code, t = key.split("|")
        if t != "도매":
            continue
        w, r = wk.get(latest), rows.get(code + "|소매", {}).get(latest)
        if w and r and w["price"] and r["price"] and r["price"] < w["price"]:
            issues["inversion"].append({"item": w["item"], "wholesale": w["price"], "retail": r["price"]})
    issues["spike"].sort(key=lambda x: -abs(x["change"]))
    issues["normal_gap"].sort(key=lambda x: -abs(x["gap"]))
    priced = [r for r in weekly if r["week"] == latest and r["price"] is not None]
    return {"week": latest, "week_label": week_label(weeks[-1]), "week_end": (weeks[-1] + dt.timedelta(days=6)).isoformat(),
            "priced_series": len(priced), "series": len([1 for r in weekly if r["week"] == latest]),
            "thresholds": {"wow_pct": WOW_ALERT, "normal_pct": NORMAL_ALERT, "daily_factor": DAILY_FACTOR},
            "no_data_13_weeks": sorted(set(no_data)), "issues": issues,
            "issue_count": sum(len(v) for k, v in issues.items() if k != "single_day")}


def main():
    today = dt.date.today()
    if len(sys.argv) > 1:
        anchor = dt.date.fromisoformat(sys.argv[1])
    else:
        this_monday = today - dt.timedelta(days=today.weekday())
        anchor = this_monday - dt.timedelta(days=7)  # last complete week
    anchor = anchor - dt.timedelta(days=anchor.weekday())
    weeks = [anchor - dt.timedelta(days=7 * i) for i in range(WEEKS - 1, -1, -1)]
    keys = [iso_key(w) for w in weeks]
    end = anchor + dt.timedelta(days=6)
    start = dt.date(end.year - 5, 1, 1)

    meta = []
    for code, cat in CATS:
        en = get(f"/home/commodities/{code}?language=2")
        km = {c["code"]: c["name"] for c in get(f"/home/commodities/{code}?language=1")}
        for c in en:
            meta.append({"code": c["code"], "cat": cat, "en": c["name"].strip(), "km": km.get(c["code"], c["name"]).replace("​", "").strip()})
    order = {m["code"]: i for i, m in enumerate(meta)}

    weekly, monthly = [], []
    recent_from = anchor - dt.timedelta(days=7 * 8)  # latest week + 8 weeks before, for the daily outlier check
    daily_recent, invalid, no_data = {}, {}, []
    m_from = dt.date(end.year - 2, end.month, 1).strftime("%Y-%m")
    for m in meta:
        for s, sko in SERIES:
            p = get(f"/home/price?locale=2&commodityCode={m['code']}&dataseries={s}&startDate={start}&endDate={end}")
            prices = (p[0] if p else {}).get("prices", [])
            wk, mo = {}, {}
            key = f"{m['code']}|{sko}"
            for x in prices:
                d = dt.date.fromisoformat(x["date"][:10])
                if d > end:
                    continue
                try:
                    v = float(x["price"])
                except (TypeError, ValueError):
                    v = None
                if v is None or not math.isfinite(v) or v <= 0 or v >= 999999:  # AMIS uses 999999.99 as a placeholder
                    if d >= anchor:
                        invalid.setdefault(key, []).append((d.isoformat(), x.get("price")))
                    continue
                if d >= recent_from:
                    daily_recent.setdefault(key, []).append((d, v))
                wk.setdefault(iso_key(d), []).append(v)
                mo.setdefault(x["date"][:7], []).append(v)
            av = lambda k: jround(sum(wk[k]) / len(wk[k])) if k in wk else None
            cur = [av(k) for k in keys]
            if all(v is None for v in cur):
                no_data.append(m["code"])
                continue
            for i, w in enumerate(weeks):
                y, n = keys[i]
                vs = [av((y - j, n)) for j in range(1, 6)]
                vs = [v for v in vs if v is not None]
                if len(vs) == 5:
                    vs = sorted(vs)[1:-1]
                weekly.append({"key": key, "code": m["code"], "cat": m["cat"], "item": KO.get(m["code"], m["en"]), "item_en": m["en"], "type": sko,
                               "week": w.isoformat(), "week_label": week_label(w), "week_month": w.strftime("%Y-%m"), "price": cur[i],
                               "last_year": av((y - 1, n)), "normal": jround(sum(vs) / len(vs)) if vs else None,
                               "days": len(wk.get(keys[i], [])), "order": order[m["code"]], "item_km": m["km"]})
            for k in sorted(mo):
                if k >= m_from:
                    monthly.append({"key": key, "code": m["code"], "item": KO.get(m["code"], m["en"]), "type": sko, "month": k,
                                    "price": jround(sum(mo[k]) / len(mo[k])), "days": len(mo[k])})
    if not weekly:
        raise RuntimeError("No weekly rows built; AMIS may have changed its API.")

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    for name, rows in (("weekly", weekly), ("monthly", monthly)):
        with open(os.path.join(ROOT, "data", name + ".json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    info = {"collected": today.isoformat(), "anchor_week": anchor.isoformat(), "weeks": [w.isoformat() for w in weeks], "weekly_rows": len(weekly), "monthly_rows": len(monthly)}
    with open(os.path.join(ROOT, "data", "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    no_data = [KO.get(c, c) for c in dict.fromkeys(no_data) if no_data.count(c) == len(SERIES)]  # no wholesale and no retail price
    report = build_report(weekly, weeks, daily_recent, invalid, no_data, anchor)
    with open(os.path.join(ROOT, "data", "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    tpl = open(os.path.join(ROOT, "site", "template.html"), encoding="utf-8").read()
    data = json.dumps({"weekly": weekly, "monthly": monthly}, ensure_ascii=False, separators=(",", ":"))
    km_date = f"{''.join(KM_DIGITS[int(c)] for c in str(today.day))} ខែ{KM_MONTHS[today.month - 1]} ឆ្នាំ{''.join(KM_DIGITS[int(c)] for c in str(today.year))}"
    html = (tpl.replace("/*PW_DATA*/null", data)
               .replace("/*DATE_KO*/", today.isoformat())
               .replace("/*DATE_EN*/", f"{today.day} {EN_MONTHS[today.month - 1]} {today.year}")
               .replace("/*DATE_KM*/", km_date))
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
