"""Emails the weekly update result and data check (data/report.json).

SMTP settings come from environment variables (GitHub Actions secrets):
  SMTP_HOST, SMTP_PORT (465 = SSL, otherwise STARTTLS), SMTP_USER, SMTP_PASS,
  MAIL_FROM (optional, defaults to SMTP_USER), MAIL_TO (optional).
Without SMTP_HOST it only prints the message (dry run).
"""
import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "https://economic-angel.github.io/cambodia-weekly-prices/"
ACTIONS = "https://github.com/economic-angel/cambodia-weekly-prices/actions"
DEFAULT_TO = "haeun.park@newma.kr"


def fmt(v):
    return "—" if v is None else f"{v:,}"


def fp(v):
    return "—" if v is None else f"{v:+.1f}%"


def build(rep, info):
    iss = rep["issues"]
    week = f"{rep['week_label']} ({rep['week'][5:].replace('-', '.')}~{rep['week_end'][5:].replace('-', '.')})"
    n = rep["issue_count"]
    subject = f"[캄보디아 농산물 가격] {rep['week_label']} 업데이트 완료 · 확인 필요 {n}건" if n else f"[캄보디아 농산물 가격] {rep['week_label']} 업데이트 완료 · 이상 없음"
    sections = [
        ("missing", "없는 값 (이번 주 가격 없음)", ["품목", "마지막 가격 주", "마지막 가격"],
         lambda x: [x["item"], x["last_priced_week"] or "—", fmt(x["last_price"])]),
        ("spike", f"튀는 값 (전주 대비 ±{rep['thresholds']['wow_pct']:.0f}% 이상)", ["품목", "전주", "금주", "등락률", "조사일수"],
         lambda x: [x["item"], fmt(x["prev"]), fmt(x["cur"]), fp(x["change"]), f"{x['days']}일"]),
        ("daily_outlier", f"일별 이상치 (직전 8주 중앙값의 {rep['thresholds']['daily_factor']:.0f}배 초과 또는 1/{rep['thresholds']['daily_factor']:.0f} 미만)", ["품목", "날짜", "가격", "8주 중앙값"],
         lambda x: [x["item"], x["date"], fmt(x["price"]), fmt(x["median_8w"])]),
        ("invalid", "잘못 입력된 값 (0, 문자, 999999.99 등 — 계산에서 제외함)", ["품목", "날짜", "입력값"],
         lambda x: [x["item"], x["date"], str(x["value"])]),
        ("normal_gap", f"평년 대비 큰 차이 (±{rep['thresholds']['normal_pct']:.0f}% 이상)", ["품목", "금주", "평년", "차이"],
         lambda x: [x["item"], fmt(x["cur"]), fmt(x["normal"]), fp(x["gap"])]),
        ("inversion", "소매가 < 도매가 역전", ["품목", "도매", "소매"],
         lambda x: [x["item"], fmt(x["wholesale"]), fmt(x["retail"])]),
    ]
    text = [f"{week} 데이터로 대시보드를 갱신했습니다.", f"가격이 있는 시계열 {rep['priced_series']}/{rep['series']}개 · 확인 필요 {n}건", ""]
    h = [f"<p>{html.escape(week)} 데이터로 대시보드를 갱신했습니다.<br>가격이 있는 시계열 <b>{rep['priced_series']}/{rep['series']}</b>개 · 확인 필요 <b>{n}</b>건</p>"]
    for k, title, cols, row in sections:
        items = iss.get(k, [])
        if not items:
            continue
        text.append(f"■ {title}: {len(items)}건")
        h.append(f"<h3 style='margin:18px 0 6px;font-size:15px'>{html.escape(title)} · {len(items)}건</h3>")
        h.append("<table style='border-collapse:collapse;font-size:13px'><tr>" + "".join(f"<th style='text-align:left;border-bottom:1px solid #ccc;padding:4px 10px'>{html.escape(c)}</th>" for c in cols) + "</tr>")
        for x in items[:30]:
            cells = row(x)
            text.append("  - " + " | ".join(cells))
            h.append("<tr>" + "".join(f"<td style='border-bottom:1px solid #eee;padding:4px 10px'>{html.escape(c)}</td>" for c in cells) + "</tr>")
        if len(items) > 30:
            text.append(f"  … 외 {len(items) - 30}건")
            h.append(f"<tr><td colspan='{len(cols)}' style='padding:4px 10px;color:#666'>… 외 {len(items) - 30}건</td></tr>")
        h.append("</table>")
        text.append("")
    if not n:
        text.append("없는 값, 튀는 값, 잘못 입력된 값이 없습니다.")
        h.append("<p>없는 값, 튀는 값, 잘못 입력된 값이 없습니다.</p>")
    notes = []
    if iss.get("single_day"):
        notes.append(f"조사일이 1일뿐인 시계열 {len(iss['single_day'])}개: " + ", ".join(iss["single_day"][:20]) + (" 외" if len(iss["single_day"]) > 20 else "") + " — 등락이 크게 나올 수 있습니다.")
    if rep.get("no_data_13_weeks"):
        notes.append("최근 13주 동안 AMIS 가격이 없는 품목(대시보드에서 제외): " + ", ".join(rep["no_data_13_weeks"]))
    for t in notes:
        text.append("※ " + t)
        h.append(f"<p style='color:#555;font-size:13px'>※ {html.escape(t)}</p>")
    text += ["", f"공개 페이지: {PAGE}", f"자동 실행 기록: {ACTIONS}", f"수집일 {info.get('collected')} · 자료: CAMAGRIMARKET / AMIS"]
    h.append(f"<p style='font-size:13px'>공개 페이지: <a href='{PAGE}'>{PAGE}</a><br>자동 실행 기록: <a href='{ACTIONS}'>{ACTIONS}</a><br><span style='color:#666'>수집일 {html.escape(str(info.get('collected')))} · 자료: CAMAGRIMARKET / AMIS</span></p>")
    body_html = "<div style='font-family:-apple-system,Segoe UI,Malgun Gothic,sans-serif;color:#1d2430;line-height:1.55'>" + "".join(h) + "</div>"
    return subject, "\n".join(text), body_html


def main():
    import sys
    if "--failed" in sys.argv:
        run = os.environ.get("RUN_URL", ACTIONS)
        subject = "[캄보디아 농산물 가격] 주간 업데이트 실패 · 확인 필요"
        text = ("이번 주 자동 업데이트가 실패해 대시보드가 갱신되지 않았습니다.\n"
                "AMIS 사이트가 응답하지 않았거나 구조가 바뀌었을 수 있습니다.\n\n"
                f"실행 기록: {run}\n같은 화면의 Run workflow로 다시 실행할 수 있습니다.")
        body_html = "<div style='font-family:-apple-system,Segoe UI,Malgun Gothic,sans-serif'>" + html.escape(text).replace("\n", "<br>") + "</div>"
    else:
        rep = json.load(open(os.path.join(ROOT, "data", "report.json"), encoding="utf-8"))
        info = json.load(open(os.path.join(ROOT, "data", "info.json"), encoding="utf-8"))
        subject, text, body_html = build(rep, info)
    to = os.environ.get("MAIL_TO") or DEFAULT_TO
    host = os.environ.get("SMTP_HOST")
    if not host:
        print("SMTP_HOST not set; dry run.\nTo:", to, "\nSubject:", subject, "\n\n" + text)
        return
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    msg.set_content(text)
    msg.add_alternative(body_html, subtype="html")
    port = int(os.environ.get("SMTP_PORT") or 587)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"]); s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx); s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"]); s.send_message(msg)
    print("Sent to", to, "-", subject)


if __name__ == "__main__":
    main()
