"""Write the rolling XMLTV guide for demo-epg.m3u.

The demo playlist (four copyright-free test streams) points its url-tvg at demo-epg.xml.
This script regenerates that file for a window around today, so the guide never runs out:
from 2 days before today (UTC midnight, for catch-up) to 14 days after. Every channel gets
twelve 2-hour programmes a day with fixed titles per slot, so the output depends only on
the date and reruns on the same day produce no diff.

Usage: python scripts/demo_epg.py [--date YYYY-MM-DD] [--out demo-epg.xml]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DAYS_BEFORE = 2
DAYS_AFTER = 14
SLOT_HOURS = 2

# (tvg-id, display name, description) -- ids must match the tvg-id values in demo-epg.m3u.
CHANNELS = [
    ("apple.demo", "Apple Test Channel", "Apple's reference HLS adaptive-bitrate test stream."),
    ("bbb.demo", "Big Buck Bunny TV", "Big Buck Bunny — Blender open movie (Creative Commons)."),
    ("tos.demo", "Tears of Steel TV", "Tears of Steel — Blender open movie (Creative Commons)."),
    ("mux.demo", "Mux Demo Channel", "Mux engineering demo stream."),
]

# One title per 2-hour slot, starting at 00:00 UTC.
SLOT_TITLES = [
    "Overnight Replay", "Early Risers", "Morning Show", "Late Morning",
    "Midday Feature", "Afternoon Matinee", "Teatime", "Early Evening",
    "Prime Time", "Late Night", "After Hours", "Night Owl",
]
assert len(SLOT_TITLES) * SLOT_HOURS == 24


def xmltv_time(t: datetime) -> str:
    return t.strftime("%Y%m%d%H%M%S +0000")


def render(today: date) -> str:
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=DAYS_BEFORE)
    end = start + timedelta(days=DAYS_BEFORE + DAYS_AFTER)
    slot = timedelta(hours=SLOT_HOURS)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="Streamline demo EPG">']
    for cid, name, _ in CHANNELS:
        lines.append(f'  <channel id="{escape(cid)}"><display-name>{escape(name)}</display-name></channel>')
    for cid, _, desc in CHANNELS:
        t = start
        while t < end:
            lines += [
                f'  <programme start="{xmltv_time(t)}" stop="{xmltv_time(t + slot)}" channel="{escape(cid)}">',
                f'    <title lang="en">{escape(SLOT_TITLES[t.hour // SLOT_HOURS])}</title>',
                f'    <desc lang="en">{escape(desc)}</desc>',
                '  </programme>',
            ]
            t += slot
    lines.append("</tv>")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", type=date.fromisoformat, help="anchor day (UTC); default: today")
    ap.add_argument("--out", type=Path, default=ROOT / "demo-epg.xml")
    args = ap.parse_args()

    today = args.date or datetime.now(timezone.utc).date()
    args.out.write_text(render(today), encoding="utf-8")
    print(f"wrote {args.out} for {today - timedelta(days=DAYS_BEFORE)} .. {today + timedelta(days=DAYS_AFTER)} (exclusive)")


if __name__ == "__main__":
    main()
