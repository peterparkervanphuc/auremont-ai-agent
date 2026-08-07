#!/usr/bin/env python3
"""Extract user prompts for this repository from local Claude Code transcripts.

Claude Code ghi transcript của mỗi phiên vào
    ~/.claude/projects/<slug-duong-dan>/<session-id>.jsonl
trong đó mỗi dòng là một record JSON. Prompt người dùng thật sự gõ nằm ở record
`type == "user"` với `message.content[*].type == "text"`.

Vì sao cần script này khi đã có hook `log_hook.py`?
  - Hook chỉ chạy đúng lúc gõ, và chỉ khi Claude Code được mở ở thư mục có
    `.claude/settings.json`. Mở nhầm thư mục cha là mất trắng cả phiên.
  - Script này quét ngược từ transcript trên đĩa nên vớt lại được cả những phiên
    hook không bắt kịp — giống cách `log_codex.py` và `log_antigravity.py` làm
    cho Codex và Antigravity.
Hai đường ghi này khử trùng lặp lẫn nhau qua `entry_id`, chạy cả hai vẫn an toàn.

Usage:
  python scripts/log_claude.py --auto            # mặc định: 24h gần nhất
  python scripts/log_claude.py --hours 72
  python scripts/log_claude.py --all             # mọi phiên, không giới hạn
  python scripts/log_claude.py --dry-run         # xem trước, không ghi

Env overrides:
  CLAUDE_PROJECTS_DIR   trỏ tới thư mục projects/ khác
  AI_LOG_DIR            nơi ghi session.jsonl (mặc định: .ai-log)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))
CLAUDE_PROJECTS = Path(
    os.environ.get("CLAUDE_PROJECTS_DIR", Path.home() / ".claude" / "projects")
)

SECRET_PATTERNS = (
    re.compile(r"\bAIza[\w-]{20,}\b"),
    re.compile(r"\bAQ\.[\w-]{20,}\b"),
    re.compile(r"(?i)\b(bearer\s+)[\w.-]{16,}"),
    re.compile(r"(?i)\b(api[ _-]?key|token|secret|password)\s*([=:])\s*\S+"),
)

# Khối do IDE/harness chèn vào lượt của user, không phải chữ student gõ ra.
# Giữ lại sẽ làm log đầy nhiễu và sai lệch bằng chứng "student đã hỏi gì".
_INJECTED_BLOCKS = re.compile(
    r"<(ide_opened_file|ide_selection|system-reminder|command-name|command-message|"
    r"command-args|local-command-stdout)>.*?</\1>",
    re.DOTALL,
)


def git(command: str) -> str:
    try:
        return subprocess.check_output(command.split(), text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def normalize(path: str) -> str:
    return path.strip().lower().replace("/", "\\").rstrip("\\")


def matches_repo(session_cwd: str, repo_root: str) -> bool:
    """Phiên thuộc về repo này khi cwd trùng, nằm trong, hoặc là thư mục cha của repo.

    Nhánh "thư mục cha" là chỗ quan trọng: mở Claude Code ở thư mục bao ngoài rồi
    làm việc trong repo con là tình huống thường gặp, và đó chính là lúc hook
    không chạy nên càng cần script này vớt lại.
    """
    session_cwd, repo_root = normalize(session_cwd), normalize(repo_root)
    return bool(
        session_cwd
        and repo_root
        and (
            session_cwd == repo_root
            or session_cwd.startswith(repo_root + "\\")
            or repo_root.startswith(session_cwd + "\\")
        )
    )


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def logged_ids(log_dir: Path) -> set[str]:
    result: set[str] = set()
    files = [log_dir / "session.jsonl"]
    archive_dir = log_dir / "archive"
    if archive_dir.is_dir():
        files.extend(archive_dir.glob("*.jsonl"))
    # Batch đang chờ gửi lại cũng tính là đã log, nếu không lần quét sau sẽ nhân đôi.
    files.extend(log_dir.glob("session.pending.*.jsonl"))
    for log_file in files:
        if not log_file.exists():
            continue
        for line in log_file.read_text(encoding="utf-8-sig").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("entry_id"):
                result.add(entry["entry_id"])
    return result


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def user_text(content) -> str:
    """Ghép các mảnh text của một lượt user, bỏ tool_result và block do IDE chèn."""
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        cleaned = _INJECTED_BLOCKS.sub("", item.get("text", "")).strip()
        if cleaned:
            parts.append(cleaned)
    return "\n".join(parts).strip()


def iter_prompts(repo_root: str, cutoff: datetime | None):
    if not CLAUDE_PROJECTS.exists():
        return
    for transcript in CLAUDE_PROJECTS.rglob("*.jsonl"):
        try:
            lines = transcript.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        records = []
        session_cwd = ""
        session_id = transcript.stem
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.append(record)
            if not session_cwd and record.get("cwd"):
                session_cwd = record["cwd"]
            if record.get("sessionId"):
                session_id = record["sessionId"]

        if not matches_repo(session_cwd, repo_root):
            continue

        for record in records:
            if record.get("type") != "user":
                continue
            message = record.get("message") or {}
            timestamp = record.get("timestamp", "")
            moment = parse_timestamp(timestamp)
            if cutoff and moment and moment < cutoff:
                continue
            text = user_text(message.get("content"))
            uuid = record.get("uuid", "")
            if len(text) < 2 or not uuid:
                continue
            yield session_id, uuid, timestamp, redact(text)


def main() -> None:
    # stderr trên Windows mặc định là code page hệ thống (cp1252), làm prompt
    # tiếng Việt ở bản xem trước hiện ra thành dấu hỏi. Dữ liệu ghi xuống file
    # vẫn đúng, chỉ phần hiển thị hỏng — nhưng --dry-run mà không đọc được thì
    # coi như mất tác dụng.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Collect Claude Code user prompts")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"
    seen = logged_ids(log_dir)
    cutoff = None if args.all else datetime.now(timezone.utc) - timedelta(hours=args.hours)
    repo_root = str(Path.cwd())
    repo = git("git remote get-url origin").split("/")[-1].removesuffix(".git") or Path.cwd().name
    branch = git("git rev-parse --abbrev-ref HEAD")
    commit = git("git rev-parse --short HEAD")
    student = git("git config user.email") or os.environ.get("USERNAME", "unknown")

    entries = []
    for session_id, uuid, timestamp, prompt in iter_prompts(repo_root, cutoff):
        entry_id = f"claude-{session_id}-{uuid}"
        if entry_id in seen:
            continue
        seen.add(entry_id)
        moment = parse_timestamp(timestamp)
        entries.append(
            {
                "ts": (moment.astimezone(VN_TZ).isoformat() if moment else datetime.now(VN_TZ).isoformat()),
                "tool": "claude-code",
                "event": "UserPrompt",
                "entry_id": entry_id,
                "session_id": session_id,
                "model": "claude-code",
                "repo": repo,
                "branch": branch,
                "commit": commit,
                "student": student,
                "prompt": prompt[:1000],
                "response_summary": "",
            }
        )

    entries.sort(key=lambda entry: entry["ts"])

    if args.dry_run:
        print(f"[claude-log] Would log {len(entries)} prompt(s).", file=sys.stderr)
        for entry in entries:
            preview = entry["prompt"].replace("\n", " ")[:100]
            print(f"  {entry['ts']}  {preview}", file=sys.stderr)
        return
    if not entries:
        print("[claude-log] No new prompts.", file=sys.stderr)
        return
    with log_file.open("a", encoding="utf-8") as output:
        for entry in entries:
            output.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[claude-log] Logged {len(entries)} prompt(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
