# Cambodia Weekly Farm Price Trends

Weekly and monthly average farm prices in Cambodia, compared week on week, against the same week last year and a 5-year normal. Khmer, English and Korean.

- Data: [CAMAGRIMARKET / AMIS](https://amis.maff.gov.kh/), Ministry of Agriculture, Forestry and Fisheries (national reference prices, KHR/kg)
- Open in a language: add `#lang=km`, `#lang=en` or `#lang=ko` to the page address
- `index.html` is self-contained: the data is embedded in the page

## Weekly update

`.github/workflows/weekly-update.yml` runs every Monday at 00:10 UTC (07:10 in Cambodia, 09:10 in Korea). It runs `scripts/update.py`, which:

1. fetches daily prices for every vegetable, fruit, cereal and other-crop item from the AMIS price service,
2. builds the last 13 complete weeks (Monday to Sunday) with the same week last year and a 5-year normal (the same week over five years, leaving out the highest and lowest), plus monthly averages for the last 25 months,
3. writes `data/weekly.json`, `data/monthly.json` and `data/info.json`, and rebuilds `index.html` from `site/template.html`.

To run it by hand: Actions → Weekly price update → Run workflow (optionally give a Monday date).
