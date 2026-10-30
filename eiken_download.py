#!/usr/bin/env python3
"""Download past Eiken exams published on the official site: question booklet PDFs,
listening script PDFs, answer PDFs and listening mp3 files.

Usage:
    python3 eiken_download.py                    # all grades
    python3 eiken_download.py 2                  # grade 2 only
    python3 eiken_download.py 1 pre1 pre2plus    # several grades
    python3 eiken_download.py -o ~/eiken --list  # only list the files

Grade arguments: 1, pre1, 2, pre2plus, pre2, 3, 4, 5
Layout: <output dir>/<grade>/<year and session>/<file>
Files that already exist are skipped, so the script can be run periodically
(e.g. via cron / launchd). Requires only the Python 3.8+ standard library.
"""
import argparse
import html
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.eiken.or.jp"
PAGE_URL = BASE + "/eiken/exam/{slug}/"
USER_AGENT = "Mozilla/5.0 (eiken-past-paper-downloader)"
DELAY = 1.0  # seconds between requests, to go easy on the server

# argument -> (page path, folder name)
GRADES = {
    "1": ("grade_1", "1級"),
    "pre1": ("grade_p1", "準1級"),
    "2": ("grade_2", "2級"),
    "pre2plus": ("grade_p2plus", "準2級プラス"),
    "pre2": ("grade_p2", "準2級"),
    "3": ("grade_3", "3級"),
    "4": ("grade_4", "4級"),
    "5": ("grade_5", "5級"),
}
ALIASES = {"p1": "pre1", "p2": "pre2", "p2plus": "pre2plus", "pre2+": "pre2plus"}

# Session heading, e.g. "2026年度 第1回" (the latest one is an <h4>,
# older ones are in the <p> of a collapsible panel)
PERIOD_RE = re.compile(r"(\d{4})年度\s*第(\d)回")
# Scan session headings and download links together, in page order
TOKEN_RE = re.compile(
    r'<h4>(?P<h4>.*?)</h4>'
    r'|<div class="c-accordion-head">\s*<p>(?P<acc>.*?)</p>'
    r'|href="(?P<href>[^"]+)"',
    re.S,
)
# Only three kinds of links: question/script PDFs, answer PDFs, listening mp3s
WANTED_RE = re.compile(
    r"^(/eiken/exam/kakomon/[^?#]+\.pdf"
    r"|/eiken/result/pdf/[^?#]+\.pdf"
    r"|https://media\.eiken\.or\.jp/listening/[^?#]+\.mp3)$"
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def parse_page(page: str):
    """Return [(session folder name, file URL), ...]"""
    items, period, seen = [], None, set()
    for m in TOKEN_RE.finditer(page):
        heading = m.group("h4") or m.group("acc")
        if heading is not None:
            pm = PERIOD_RE.search(html.unescape(heading))
            if pm:
                period = f"{pm.group(1)}年度第{pm.group(2)}回"
            continue
        href = html.unescape(m.group("href"))
        if period and WANTED_RE.match(href):
            url = urllib.parse.urljoin(BASE, href)
            if url not in seen:
                seen.add(url)
                items.append((period, url))
    return items


def download(url: str, dest: Path) -> str:
    """Return 'ok', 'skip' or 'fail'."""
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        time.sleep(DELAY)
        tmp.write_bytes(fetch(url))
        tmp.rename(dest)  # rename only when complete, so no partial files are left behind
        return "ok"
    except (urllib.error.URLError, OSError) as e:
        tmp.unlink(missing_ok=True)
        print(f"    Failed: {url} ({e})", file=sys.stderr)
        return "fail"


def main() -> int:
    ap = argparse.ArgumentParser(description="Download past Eiken exams (PDFs + listening audio)")
    ap.add_argument("grades", nargs="*", metavar="GRADE",
                    help="1 pre1 2 pre2plus pre2 3 4 5; all grades if omitted")
    ap.add_argument("-o", "--output", default="eiken_past_papers",
                    help="output directory (default: ./eiken_past_papers)")
    ap.add_argument("--list", action="store_true", help="only list files, do not download")
    args = ap.parse_args()

    keys = []
    for g in args.grades:
        g = ALIASES.get(g.lower(), g.lower())
        if g not in GRADES:
            ap.error(f"unknown grade: {g} (choose from: {', '.join(GRADES)})")
        if g not in keys:
            keys.append(g)
    keys = keys or list(GRADES)

    out = Path(args.output).expanduser()
    counts = {"ok": 0, "skip": 0, "fail": 0}
    for key in keys:
        slug, folder = GRADES[key]
        print(f"== {folder}")
        try:
            time.sleep(DELAY)
            items = parse_page(fetch(PAGE_URL.format(slug=slug)).decode("utf-8"))
        except (urllib.error.URLError, OSError) as e:
            print(f"  Could not fetch page: {e}", file=sys.stderr)
            counts["fail"] += 1
            continue
        if not items:
            print("  No files found (the site structure may have changed)", file=sys.stderr)
            continue
        for period, url in items:
            name = Path(urllib.parse.urlparse(url).path).name
            dest = out / folder / period / name
            if args.list:
                print(f"  {dest.relative_to(out)}  <-  {url}")
                continue
            status = download(url, dest)
            counts[status] += 1
            if status == "ok":
                print(f"  ✓ {dest.relative_to(out)}")
    if not args.list:
        print(f"\nDone: {counts['ok']} downloaded, {counts['skip']} already present, {counts['fail']} failed")
        print(f"Saved to: {out.resolve()}")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
