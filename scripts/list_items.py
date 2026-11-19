"""Lists every AMIS item in every category, with how many wholesale/retail prices it has in the last 12 months."""
import datetime as dt
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from update import get  # noqa: E402

end = dt.date.today(); start = end - dt.timedelta(days=365)
cats = get("/home/categories?language=2")
for c in cats:
    items = get(f"/home/commodities/{c['code']}?language=2")
    print(f"\n== {c['code']} {c['name'].strip()} ({len(items)} items)")
    for it in items:
        counts = []
        for s in ("WP", "RP"):
            p = get(f"/home/price?locale=2&commodityCode={it['code']}&dataseries={s}&startDate={start}&endDate={end}")
            pr = (p[0] if p else {}).get("prices", [])
            counts.append(f"{s} {len(pr)}" + (f" (last {pr[-1]['date'][:10]})" if pr else ""))
        print(f"{it['code']}\t{it['name'].strip()}\t" + " | ".join(counts))
