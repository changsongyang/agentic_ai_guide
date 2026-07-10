#!/usr/bin/env python3
"""Lightweight Markdown project checks for book repositories."""

from __future__ import annotations

import ast
import re
import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {
    ".agent",
    ".git",
    ".mdpress",
    "_book",
    "_site",
    "dist",
    "node_modules",
}
LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+(?:\s+\"[^\"]*\")?)\)")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
VOLATILE_META_RE = re.compile(
    r"`verified_at`:\s*(\d{4}-\d{2}-\d{2})\s*·\s*"
    r"`expires_at`:\s*(\d{4}-\d{2}-\d{2})\s*·\s*"
    r"`ttl_days`:\s*(\d+)"
)
VOLATILE_STATUS_RE = re.compile(
    r"<!--\s*volatile-status:\s*id=([^\s]+)\s+status=([^\s]+)\s*-->"
)
ANGLE_PLACEHOLDER_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_.-]*)>")


def iter_markdown_files(root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)


def display_path(path: Path, root: Path = ROOT) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def strip_fenced_blocks(text: str) -> str:
    output: list[str] = []
    in_fence = False
    fence_marker = ""
    fence_len = 0
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            char = marker[0]
            length = len(marker)
            if not in_fence:
                in_fence = True
                fence_marker = char
                fence_len = length
            elif char == fence_marker and length >= fence_len:
                in_fence = False
            output.append("")
            continue
        output.append("" if in_fence else line)
    return "\n".join(output)


def check_fences(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    stack: list[tuple[str, int, int]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = FENCE_RE.match(line)
        if not match:
            continue
        marker = match.group(1)
        char = marker[0]
        length = len(marker)
        if not stack:
            stack.append((char, length, line_no))
            continue
        open_char, open_len, _ = stack[-1]
        if char == open_char and length >= open_len:
            stack.pop()
        else:
            stack.append((char, length, line_no))
    for _, _, line_no in stack:
        issues.append(f"{path.relative_to(ROOT)}:{line_no}: unclosed fenced code block")
    return issues


def is_local_target(target: str) -> bool:
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and not target.startswith("#")


def normalize_target(raw_target: str) -> str:
    target = raw_target.strip()
    if " " in target and target.count('"') >= 2:
        target = target.split(" ", 1)[0]
    return unquote(target.split("#", 1)[0])


def check_links(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    body = strip_fenced_blocks(text)
    for match in LINK_RE.finditer(body):
        raw_target = match.group(2).strip()
        target = normalize_target(raw_target)
        if not target or not is_local_target(raw_target):
            continue
        target_path = (path.parent / target).resolve()
        try:
            target_path.relative_to(ROOT)
        except ValueError:
            continue
        if not target_path.exists():
            line_no = body[: match.start()].count("\n") + 1
            issues.append(
                f"{path.relative_to(ROOT)}:{line_no}: missing local link target: {raw_target}"
            )
    return issues


def check_summary_links() -> list[str]:
    summary = ROOT / "SUMMARY.md"
    if not summary.exists():
        return []
    return check_links(summary, summary.read_text(encoding="utf-8", errors="ignore"))


def check_volatile_facts(
    path: Path = ROOT / "12_appendix" / "12.5_volatile_facts.md",
    today: date | None = None,
) -> list[str]:
    """Fail closed when the fast-changing-facts ledger is stale or ambiguous."""

    issues: list[str] = []
    name = display_path(path)
    if not path.is_file():
        return [f"{name}: volatile facts ledger is missing"]

    text = path.read_text(encoding="utf-8", errors="ignore")
    metadata = VOLATILE_META_RE.search(text)
    if metadata is None:
        issues.append(f"{name}: volatile facts metadata is missing")
    else:
        try:
            verified_at = date.fromisoformat(metadata.group(1))
            expires_at = date.fromisoformat(metadata.group(2))
        except ValueError as exc:
            issues.append(f"{name}: invalid volatile facts date: {exc}")
        else:
            ttl_days = int(metadata.group(3))
            current_date = today or date.today()
            if expires_at <= verified_at:
                issues.append(
                    f"{name}: volatile facts expires_at must be after verified_at"
                )
            if ttl_days != 30 or expires_at != verified_at + timedelta(days=30):
                issues.append(
                    f"{name}: volatile facts TTL must describe exactly 30 days"
                )
            if verified_at > current_date:
                issues.append(
                    f"{name}: volatile facts verified_at is in the future "
                    f"({verified_at.isoformat()})"
                )
            if current_date > expires_at:
                issues.append(
                    f"{name}: volatile facts ledger expired on {expires_at.isoformat()}"
                )

    statuses = VOLATILE_STATUS_RE.findall(text)
    if not statuses:
        issues.append(f"{name}: volatile facts status metadata is missing")
    for fact_id, status in statuses:
        if status == "open-conflict":
            issues.append(f"{name}: {fact_id} has an unresolved conflict")
        elif status not in {"current", "resolved-conflict"}:
            issues.append(f"{name}: {fact_id} has unknown status {status!r}")
    return issues


def check_python_fences(root: Path = ROOT) -> list[str]:
    """Parse every runnable Python fence and reject template placeholders."""

    issues: list[str] = []
    for path in iter_markdown_files(root):
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        index = 0
        while index < len(lines):
            opening = FENCE_RE.match(lines[index])
            if opening is None:
                index += 1
                continue

            marker = opening.group(1)
            info = lines[index][opening.end() :].strip().split()
            start_line = index + 1
            index += 1
            body: list[str] = []
            while index < len(lines):
                closing = FENCE_RE.match(lines[index])
                if (
                    closing is not None
                    and closing.group(1)[0] == marker[0]
                    and len(closing.group(1)) >= len(marker)
                ):
                    break
                body.append(lines[index])
                index += 1
            index += 1

            if not info or info[0].lower() not in {"python", "py"}:
                continue

            flags = {item.lower() for item in info[1:]}
            if "non-runnable" in flags:
                previous = start_line - 2
                while previous >= 0 and not lines[previous].strip():
                    previous -= 1
                introduction = lines[previous] if previous >= 0 else ""
                if "伪代码" not in introduction or "不可直接运行" not in introduction:
                    issues.append(
                        f"{display_path(path, root)}:{start_line}: non-runnable Python "
                        "must be introduced as pseudocode that cannot run directly"
                    )
                continue

            code = textwrap.dedent("\n".join(body))
            for match in ANGLE_PLACEHOLDER_RE.finditer(code):
                token = match.group(1)
                if re.search(rf"</{re.escape(token)}\s*>", code):
                    continue
                line_no = start_line + code[: match.start()].count("\n") + 1
                issues.append(
                    f"{display_path(path, root)}:{line_no}: angle-bracket placeholder "
                    f"<{token}> is not valid runnable Python configuration"
                )
            try:
                ast.parse(code, filename=str(path))
            except SyntaxError as exc:
                line_no = start_line + (exc.lineno or 1)
                issues.append(
                    f"{display_path(path, root)}:{line_no}: invalid Python syntax: "
                    f"{exc.msg}"
                )
    return issues


def main() -> int:
    issues: list[str] = []
    files = iter_markdown_files()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        issues.extend(check_fences(path, text))
        issues.extend(check_links(path, text))
    issues.extend(check_summary_links())
    issues.extend(check_volatile_facts())
    issues.extend(check_python_fences())

    if issues:
        print("\n".join(sorted(set(issues))))
        print(f"\n{len(set(issues))} issue(s) found across {len(files)} Markdown files.")
        return 1
    print(f"All {len(files)} Markdown files passed project checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
