import http.client
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

BASE_URL = "https://daily.juya.uk/markdown"
START_DATE = date(2026, 11,27)
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "mds"
USER_AGENT = "Mozilla/5.0 (compatible; juya-md-archiver/1.0)"


def fetch(url: str, retries: int = 3) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if (exc.code < 500 and exc.code != 429) or attempt == retries:
                raise
        except (OSError, http.client.HTTPException):
            if attempt == retries:
                raise
        time.sleep(attempt)
    raise RuntimeError("unreachable")


def date_range(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = missing = failed = 0

    for day in date_range(START_DATE, date.today()):
        name = f"{day.isoformat()}.md"
        dest = OUTPUT_DIR / name

        if dest.exists():
            skipped += 1
            print(f"{name}: 已存在")
            continue

        try:
            content = fetch(f"{BASE_URL}/{name}")
        except (OSError, http.client.HTTPException) as exc:
            print(f"{name}: 下载失败（{exc}）", file=sys.stderr)
            failed += 1
            continue

        if content is None:
            print(f"{name}: 不存在，跳过")
            missing += 1
        else:
            dest.write_bytes(content)
            print(f"{name}: 已下载")
            downloaded += 1

    print(
        f"\n完成：下载 {downloaded} 个，已存在 {skipped} 个，"
        f"缺失 {missing} 个，失败 {failed} 个"
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
