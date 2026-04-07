#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
import subprocess
import smtplib
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.message import EmailMessage
from html import unescape
from pathlib import Path
from typing import Dict, List, Tuple

FEED_URLS = [
    "https://www.natronacounty-wy.gov/RSSFeed.aspx?ModID=76&CID=All-0",
    "https://www.natronacounty-wy.gov/RSSFeed.aspx?ModID=1&CID=All-newsflash.xml",
    "https://www.natronacounty-wy.gov/RSSFeed.aspx?ModID=65&CID=All-0",
]

PROCUREMENT_TERMS = {
    "rfp": 8,
    "request for proposal": 8,
    "request for proposals": 8,
    "rfq": 8,
    "request for qualifications": 8,
    "invitation to bid": 9,
    "itb": 8,
    "bid": 6,
    "bids": 6,
    "solicitation": 8,
    "addendum": 5,
    "pre-bid": 9,
    "contract award": 7,
    "sealed bid": 9,
}

BUILDING_SUPPLY_TERMS = {
    "window": 10,
    "windows": 10,
    "door": 10,
    "doors": 10,
    "glazing": 9,
    "storefront": 9,
    "hardware": 6,
    "framing": 6,
    "finish carpentry": 8,
    "entry system": 8,
    "building envelope": 7,
}

PROJECT_CONTEXT_TERMS = {
    "construction": 5,
    "renovation": 6,
    "remodel": 6,
    "replacement": 7,
    "facility": 4,
    "maintenance": 4,
    "courthouse": 5,
    "detention": 4,
    "school": 4,
    "library": 4,
    "public works": 5,
}

NEGATIVE_TERMS = {
    "vacancy": -3,
    "fire restriction": -3,
    "festival": -2,
    "meeting": -2,
}

RSS_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M %z",
]

HTTP_TIMEOUT_SECONDS = 18
MAX_PAGE_CHARS = 35000


@dataclass
class Opportunity:
    uid: str
    title: str
    link: str
    source_feed: str
    published: str
    age_days: int
    score: int
    level: str
    reason_terms: List[str]
    summary: str


def fetch_text(url: str) -> str:
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return Path(url).read_text()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "WyomingBuildingSupplyOpportunityScanner/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9,*/*;q=0.8",
        },
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS, context=context) as response:
            data = response.read()
        return data.decode("utf-8", errors="replace")
    except Exception:
        # Fallback for environments where Python's resolver/SSL path is blocked.
        result = subprocess.run(
            ["curl", "-L", "--fail", "--silent", "--show-error", url],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout


def strip_html(html_text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_pub_date(raw: str) -> dt.datetime:
    for fmt in RSS_DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {raw}")


def score_text(text: str) -> Tuple[int, List[str]]:
    haystack = f" {text.lower()} "
    score = 0
    matched = []

    def apply_terms(term_weights: Dict[str, int], prefix: str) -> None:
        nonlocal score
        for term, weight in term_weights.items():
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, haystack):
                score += weight
                matched.append(f"{prefix}:{term}")

    apply_terms(PROCUREMENT_TERMS, "proc")
    apply_terms(BUILDING_SUPPLY_TERMS, "fit")
    apply_terms(PROJECT_CONTEXT_TERMS, "ctx")
    apply_terms(NEGATIVE_TERMS, "neg")

    return score, matched


def level_for_score(score: int) -> str:
    if score >= 20:
        return "HIGH"
    if score >= 11:
        return "MEDIUM"
    return "LOW"


def make_uid(title: str, link: str, published: str) -> str:
    digest = hashlib.sha256(f"{title}|{link}|{published}".encode("utf-8")).hexdigest()
    return digest[:16]


def fetch_feed_items(feed_url: str) -> List[Dict[str, str]]:
    xml_text = fetch_text(feed_url)
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        items.append(
            {
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "description": description,
            }
        )
    return items


def load_seen_ids(path: Path) -> set:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return set(str(x) for x in data)
    except json.JSONDecodeError:
        pass
    return set()


def save_seen_ids(path: Path, ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(set(ids)), indent=2))


def generate_report(opps: List[Opportunity], new_ids: set, generated_at: dt.datetime) -> Tuple[str, str]:
    json_payload = {
        "generated_at": generated_at.isoformat(),
        "total_items": len(opps),
        "new_items": len([o for o in opps if o.uid in new_ids]),
        "high_priority": len([o for o in opps if o.level == "HIGH"]),
        "medium_priority": len([o for o in opps if o.level == "MEDIUM"]),
        "items": [o.__dict__ for o in opps],
    }

    lines = []
    lines.append(f"# Natrona County Opportunity Report ({generated_at.date().isoformat()})")
    lines.append("")
    lines.append(f"- Total flagged: **{len(opps)}**")
    lines.append(f"- New since last run: **{len([o for o in opps if o.uid in new_ids])}**")
    lines.append(f"- HIGH: **{len([o for o in opps if o.level == 'HIGH'])}**")
    lines.append(f"- MEDIUM: **{len([o for o in opps if o.level == 'MEDIUM'])}**")
    lines.append("")

    if not opps:
        lines.append("No medium/high-fit opportunities found in the selected time window.")

    for idx, opp in enumerate(opps, start=1):
        novelty = "NEW" if opp.uid in new_ids else "SEEN"
        lines.append(f"## {idx}. [{opp.level}] {opp.title} ({novelty})")
        lines.append(f"- Score: `{opp.score}`")
        lines.append(f"- Published: `{opp.published}` ({opp.age_days} day(s) ago)")
        lines.append(f"- Link: {opp.link}")
        lines.append(f"- Source Feed: {opp.source_feed}")
        lines.append(f"- Matched Terms: `{', '.join(opp.reason_terms[:12])}`")
        lines.append(f"- Summary: {opp.summary}")
        lines.append("")

    return json.dumps(json_payload, indent=2), "\n".join(lines)


def summarize_text(text: str, max_len: int = 220) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def send_email_alert(
    recipients_csv: str,
    opportunities: List[Opportunity],
    generated_at: dt.datetime,
) -> None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        print("WARN: Skipped email alerts. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.")
        return

    recipients = [x.strip() for x in recipients_csv.split(",") if x.strip()]
    if not recipients:
        print("WARN: No valid --notify-email recipients supplied.")
        return

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"Natrona Opportunity Alert - {len(opportunities)} New Item(s) - {generated_at.date().isoformat()}"

    body_lines = [
        "New Natrona County opportunities matched your criteria.",
        "",
        f"Generated (UTC): {generated_at.isoformat()}",
        f"Count: {len(opportunities)}",
        "",
    ]

    for idx, opp in enumerate(opportunities, start=1):
        body_lines.append(f"{idx}. [{opp.level}] {opp.title}")
        body_lines.append(f"   Score: {opp.score}")
        body_lines.append(f"   Published: {opp.published}")
        body_lines.append(f"   Link: {opp.link}")
        body_lines.append("")

    body_lines.append("Report: reports/opportunities_latest.md")
    msg.set_content("\n".join(body_lines))

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=25) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=25) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

    print(f"Email alert sent to: {', '.join(recipients)}")


def build_email_preview(opportunities: List[Opportunity], generated_at: dt.datetime) -> Tuple[str, str]:
    subject = f"Natrona Opportunity Alert - {len(opportunities)} New Item(s) - {generated_at.date().isoformat()}"
    body_lines = [
        "New Natrona County opportunities matched your criteria.",
        "",
        f"Generated (UTC): {generated_at.isoformat()}",
        f"Count: {len(opportunities)}",
        "",
    ]

    for idx, opp in enumerate(opportunities, start=1):
        body_lines.append(f"{idx}. [{opp.level}] {opp.title}")
        body_lines.append(f"   Score: {opp.score}")
        body_lines.append(f"   Published: {opp.published}")
        body_lines.append(f"   Link: {opp.link}")
        body_lines.append("")

    body_lines.append("Report: reports/opportunities_latest.md")
    return subject, "\n".join(body_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Natrona County RSS feeds for relevant bid opportunities.")
    parser.add_argument("--days", type=int, default=60, help="Only include items newer than this many days.")
    parser.add_argument("--max-items", type=int, default=250, help="Max RSS items to process across all feeds.")
    parser.add_argument("--min-level", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
    parser.add_argument(
        "--feed-url",
        action="append",
        default=[],
        help="Custom feed URL or local XML file path. Repeat flag to provide multiple feeds.",
    )
    parser.add_argument(
        "--notify-email",
        default="",
        help="Comma-separated emails to alert when new opportunities are found.",
    )
    parser.add_argument(
        "--notify-on-level",
        choices=["LOW", "MEDIUM", "HIGH"],
        default="MEDIUM",
        help="Minimum level that triggers notification email.",
    )
    parser.add_argument(
        "--simulate-email",
        action="store_true",
        help="Preview alert email content without sending.",
    )
    parser.add_argument(
        "--force-notify-current",
        action="store_true",
        help="Treat current scan results as notifiable for testing.",
    )
    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    min_age = dt.timedelta(days=args.days)
    level_threshold = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

    seen_ids_path = Path("state/seen_ids.json")
    old_seen = load_seen_ids(seen_ids_path)

    scanned = []
    feed_sources = args.feed_url if args.feed_url else FEED_URLS

    for feed_url in feed_sources:
        try:
            scanned.extend((feed_url, item) for item in fetch_feed_items(feed_url))
        except Exception as exc:
            print(f"WARN: Failed feed {feed_url}: {exc}")

    scanned = scanned[: args.max_items]
    opportunities: List[Opportunity] = []
    processed_ids = []

    for feed_url, item in scanned:
        if not item["title"] or not item["link"] or not item["pub_date"]:
            continue
        try:
            published = parse_pub_date(item["pub_date"])
        except ValueError:
            continue

        if now - published.astimezone(dt.timezone.utc) > min_age:
            continue

        combined = f"{item['title']}\n{item['description']}"

        page_text = ""
        try:
            page_html = fetch_text(item["link"])
            page_text = strip_html(page_html)[:MAX_PAGE_CHARS]
        except Exception:
            page_text = ""

        score, matched = score_text(f"{combined}\n{page_text}")
        level = level_for_score(score)

        if level_threshold[level] < level_threshold[args.min_level]:
            continue

        uid = make_uid(item["title"], item["link"], item["pub_date"])
        processed_ids.append(uid)
        age_days = (now - published.astimezone(dt.timezone.utc)).days

        opportunities.append(
            Opportunity(
                uid=uid,
                title=item["title"],
                link=item["link"],
                source_feed=feed_url,
                published=published.isoformat(),
                age_days=age_days,
                score=score,
                level=level,
                reason_terms=matched,
                summary=summarize_text(item["description"] or page_text),
            )
        )

    opportunities.sort(key=lambda o: (o.level, o.score, o.published), reverse=True)

    new_ids = set(processed_ids) - old_seen
    report_json, report_md = generate_report(opportunities, new_ids, now)

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "opportunities_latest.json").write_text(report_json)
    (reports_dir / "opportunities_latest.md").write_text(report_md)

    save_seen_ids(seen_ids_path, list(old_seen.union(set(processed_ids))))

    if args.notify_email or args.simulate_email:
        threshold = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        base_items = opportunities if args.force_notify_current else [o for o in opportunities if o.uid in new_ids]
        notify_items = [o for o in base_items if threshold[o.level] >= threshold[args.notify_on_level]]
        if notify_items:
            if args.simulate_email:
                preview_to = args.notify_email.strip() or "simulation@example.com"
                subject, body = build_email_preview(notify_items, now)
                print(f"SIMULATION ONLY: would send to {preview_to}")
                print(f"SIMULATION SUBJECT: {subject}")
                print("SIMULATION BODY START")
                print(body)
                print("SIMULATION BODY END")
            elif args.notify_email:
                send_email_alert(args.notify_email, notify_items, now)
        else:
            print("No new opportunities met notification threshold.")

    print(f"Scanned items: {len(scanned)}")
    print(f"Opportunities ({args.min_level}+): {len(opportunities)}")
    print("Report: reports/opportunities_latest.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
