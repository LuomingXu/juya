import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "mds"
OUTPUT_DIR = ROOT / "corpus"

OVERVIEW_TITLE = "概览"
DISCLAIMER_MARKER = "内容由AI辅助创作"
LINKED_HEADING = re.compile(r"^### \[(.+?)\]\((https?://.+)\)\s+`#(\d+)`\s*$")
UNLINKED_HEADING = re.compile(r"^### (.+?)\s+`#(\d+)`\s*$")
ID_AT_END = re.compile(r"`#(\d+)`\s*$")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")
PUNCT_GAP = re.compile(r"[ \t]+(?=[，。；：、！？）】”])")
OPEN_GAP = re.compile(r"(?<=[（【“])[ \t]+")
RELATED_HEADERS = {"相关链接：", "相关链接:"}
RELATED_URL = re.compile(r"\]\((https?://.+)\)\s*$")


@dataclass
class Item:
    category: str
    number: int
    title: str
    url: str | None
    summary: str
    lead: str
    content: str
    links: list[str]


def clean_inline(text: str) -> str:
    text = IMAGE.sub("", text)
    text = text.replace("**", "").replace("`", "")
    text = CJK_GAP.sub("", text)
    text = PUNCT_GAP.sub("", text)
    text = OPEN_GAP.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_heading(
    block: list[str], position: int
) -> tuple[str, str | None, int, list[str], list[str]]:
    heading = block[0]
    match = LINKED_HEADING.match(heading)
    if match:
        return clean_inline(match.group(1)), match.group(2), int(match.group(3)), block[1:], []

    match = UNLINKED_HEADING.match(heading)
    if match:
        return clean_inline(match.group(1)), None, int(match.group(2)), block[1:], []

    for offset, line in enumerate(block[1:6], start=1):
        match = ID_AT_END.search(line.strip())
        if match:
            lead_lines = [value.strip() for value in block[1 : offset + 1]]
            lead_lines[-1] = ID_AT_END.sub("", lead_lines[-1]).strip()
            return (
                clean_inline(heading[4:].strip()),
                None,
                int(match.group(1)),
                block[offset + 1 :],
                lead_lines,
            )

    return clean_inline(heading[4:].strip()), None, position, block[1:], []


def parse_summary(lines: list[str]) -> tuple[str, list[str]]:
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1

    summary_lines = []
    while index < len(lines):
        stripped = lines[index].lstrip()
        if not stripped.startswith(">"):
            break
        summary_lines.append(stripped[1:].strip())
        index += 1

    summary = clean_inline(" ".join(part for part in summary_lines if part))
    return summary, lines[index:]


def split_related(lines: list[str]) -> tuple[list[str], list[str]]:
    for index, line in enumerate(lines):
        if line.strip() not in RELATED_HEADERS:
            continue

        links = []
        for raw in lines[index + 1 :]:
            match = RELATED_URL.search(raw.strip())
            if match:
                link = match.group(1).strip()
                if link not in links:
                    links.append(link)
        return lines[:index], links

    return lines, []


def format_content(lines: list[str]) -> str:
    output: list[str] = []
    in_fence = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_fence:
                output.append(stripped)
                in_fence = False
                output.append("")
            else:
                if output and output[-1] != "":
                    output.append("")
                output.append(stripped)
                in_fence = True
            continue

        if in_fence:
            output.append(line)
            continue

        if not stripped:
            if output and output[-1] != "":
                output.append("")
            continue

        if stripped == "---" or DISCLAIMER_MARKER in stripped:
            continue

        without_images = IMAGE.sub("", line).strip()
        if without_images:
            output.append(clean_inline(without_images))

    while output and output[0] == "":
        output.pop(0)
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output)


def parse_item(category: str, block: list[str], position: int) -> Item:
    title, url, number, rest, lead_lines = parse_heading(block, position)
    summary, rest = parse_summary(rest)
    body_lines, raw_links = split_related(rest)
    links = [link for link in raw_links if link != url]

    return Item(
        category=category,
        number=number,
        title=title,
        url=url,
        summary=summary,
        lead=format_content(lead_lines),
        content=format_content(body_lines),
        links=links,
    )


def parse_items(lines: list[str]) -> list[Item]:
    raw_items: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    category: str | None = None

    for line in lines:
        if line.startswith("## "):
            if current is not None:
                raw_items.append((category, current))
                current = None
            name = line[3:].strip()
            category = None if name == OVERVIEW_TITLE else name
        elif line.startswith("### "):
            if current is not None:
                raw_items.append((category, current))
                current = None
            if category is not None:
                current = [line]
        elif current is not None:
            current.append(line)

    if current is not None:
        raw_items.append((category, current))

    return [
        parse_item(category, block, position)
        for position, (category, block) in enumerate(raw_items, start=1)
    ]


def extract_header(lines: list[str], path: Path) -> tuple[str, str | None]:
    title = path.stem
    video = None

    for line in lines:
        if line.startswith("## "):
            break
        if line.startswith("# "):
            title = line[2:].strip()
        elif "视频版" in line and video is None:
            video = clean_inline(line)

    return title, video


def render_document(path: Path, lines: list[str], items: list[Item]) -> str:
    title, video = extract_header(lines, path)
    categories = list(dict.fromkeys(item.category for item in items))

    output = [
        "---",
        f"date: {path.stem}",
        f"title: {title}",
    ]
    if categories:
        output.append("categories:")
        output.extend(f"  - {category}" for category in categories)
    else:
        output.append("categories: []")
    output.extend(["items: " + str(len(items)), "---", "", f"# {title}", ""])

    if video:
        output.extend([video, ""])

    current_category: str | None = None
    for item in items:
        if item.category != current_category:
            current_category = item.category
            output.extend([f"## {current_category}", ""])

        if item.url:
            heading = f"### [{item.title}]({item.url}) `#{item.number}`"
        else:
            heading = f"### {item.title} `#{item.number}`"
        output.extend([heading, ""])

        if item.summary:
            output.extend([f"> {item.summary}", ""])
        if item.lead:
            output.extend([item.lead, ""])
        if item.content:
            output.extend([item.content, ""])
        if item.links:
            output.append("相关链接：")
            output.extend(f"- {link}" for link in item.links)
            output.append("")

    return "\n".join(output).rstrip() + "\n"


def convert_file(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    items = parse_items(lines)
    if not items:
        raise ValueError("未解析到任何条目")

    markdown = render_document(path, lines, items)
    (OUTPUT_DIR / path.name).write_text(markdown, encoding="utf-8")
    return len(items)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(SOURCE_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"未找到 Markdown 文件: {SOURCE_DIR}")

    total_items = 0
    failures = []

    for index, path in enumerate(files, start=1):
        try:
            item_count = convert_file(path)
        except (OSError, ValueError) as exc:
            failures.append(path.name)
            print(f"[{index}/{len(files)}] {path.name}: 失败 - {exc}", file=sys.stderr)
            continue

        total_items += item_count
        print(f"[{index}/{len(files)}] {path.name}: {item_count} 条")

    succeeded = len(files) - len(failures)
    print(
        f"\n完成：成功 {succeeded}/{len(files)} 个文件，"
        f"共 {total_items} 条，失败 {len(failures)} 个"
    )
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
