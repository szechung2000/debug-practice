"""Read Claude Code session transcripts and compute interaction metrics.

Claude Code writes one JSONL file per session under ~/.claude/projects/<dir>/.
Each line is an event. The fields this module uses are:
  type       "user" | "assistant" (other types are skipped)
  timestamp  ISO-8601 string
  cwd        working directory of the session
  message    {"role": ..., "content": str | [blocks]}
Blocks are {"type": "text"}, {"type": "tool_use", "name", "input"},
{"type": "tool_result", "content", "is_error"} or {"type": "thinking"}.
The parser is defensive: unknown shapes are skipped, not fatal.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
RUN_RE = re.compile(r"\b(python3?|pytest|make|bash|sh|duckdb|sqlite3)\b")
CHALLENGE_RE = re.compile(
    r"\b(why|are you sure|prove|evidence|how do you know|show me|double.?check|confirm|"
    r"reproduce|repro|what if|wrong|incorrect|not right|that's not|disagree)\b", re.I)
PLAN_RE = re.compile(
    r"(plan|hypothes|root cause|investigat|don'?t (edit|change|fix|touch)|before (you )?"
    r"(edit|chang|fix)|read.?only|explain|walk me through|diagnos)", re.I)
REJECT_MARKERS = ("doesn't want to proceed", "rejected", "user denied", "was denied")
INTERRUPT_MARKER = "[Request interrupted by user"


@dataclass
class Event:
    ts: datetime
    kind: str          # user_prompt | assistant_text | tool_use | tool_result | command
    text: str = ""
    tool: str = ""
    tool_input: dict = field(default_factory=dict)
    is_error: bool = False


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_transcripts(repo_root: Path, since: datetime) -> list[Path]:
    root = CLAUDE_HOME / "projects"
    if not root.exists():
        return []
    repo = str(repo_root.resolve())
    found = []
    for path in root.glob("*/*.jsonl"):
        if datetime.fromtimestamp(path.stat().st_mtime, since.tzinfo) < since:
            continue
        with path.open(errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 50:
                    break
                try:
                    cwd = json.loads(line).get("cwd", "")
                except json.JSONDecodeError:
                    continue
                if cwd and (cwd == repo or cwd.startswith(repo + os.sep)):
                    found.append(path)
                    break
    return sorted(found, key=lambda p: p.stat().st_mtime)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def load_events(paths: list[Path], since: datetime) -> list[Event]:
    events: list[Event] = []
    for path in paths:
        for line in path.read_text(errors="replace").splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(raw.get("timestamp"))
            if ts is None or ts < since or raw.get("type") not in ("user", "assistant"):
                continue
            msg = raw.get("message") or {}
            content = msg.get("content")
            if raw["type"] == "user":
                if isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            events.append(Event(ts, "tool_result", _text_of(b.get("content")),
                                                is_error=bool(b.get("is_error"))))
                    continue
                text = _text_of(content)
                if raw.get("isMeta") or text.lstrip().startswith(("<command-", "<local-command", "<system-reminder")):
                    events.append(Event(ts, "command", text))
                elif text.strip():
                    events.append(Event(ts, "user_prompt", text))
            else:
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        events.append(Event(ts, "assistant_text", b["text"]))
                    elif b.get("type") == "tool_use":
                        events.append(Event(ts, "tool_use", tool=b.get("name", ""),
                                            tool_input=b.get("input") or {}))
    events.sort(key=lambda e: e.ts)
    return events


def compute_metrics(events: list[Event]) -> dict:
    prompts = [e for e in events if e.kind == "user_prompt"]
    tools = [e for e in events if e.kind == "tool_use"]
    results = [e for e in events if e.kind == "tool_result"]
    edits = [e for e in tools if e.tool in EDIT_TOOLS]
    runs = [e for e in tools if e.tool == "Bash" and RUN_RE.search(str(e.tool_input.get("command", "")))]
    first_edit = edits[0].ts if edits else None
    last_edit = edits[-1].ts if edits else None
    tool_counts: dict[str, int] = {}
    for e in tools:
        tool_counts[e.tool] = tool_counts.get(e.tool, 0) + 1
    duration = (events[-1].ts - events[0].ts).total_seconds() / 60 if events else 0.0
    return {
        "duration_minutes": round(duration, 1),
        "user_prompts": len(prompts),
        "avg_prompt_chars": round(sum(len(p.text) for p in prompts) / len(prompts)) if prompts else 0,
        "first_prompt_chars": len(prompts[0].text) if prompts else 0,
        "tool_calls": len(tools),
        "tool_counts": tool_counts,
        "edit_calls": len(edits),
        "code_runs_before_first_edit": sum(1 for r in runs if first_edit is None or r.ts < first_edit),
        "code_runs_after_last_edit": sum(1 for r in runs if last_edit is not None and r.ts > last_edit),
        "minutes_to_first_edit": round((first_edit - events[0].ts).total_seconds() / 60, 1) if first_edit else None,
        "prompts_asking_plan_or_rca": sum(1 for p in prompts if PLAN_RE.search(p.text)),
        "prompts_challenging_ai": sum(1 for p in prompts if CHALLENGE_RE.search(p.text)),
        "tool_rejections": sum(1 for r in results if any(m in r.text for m in REJECT_MARKERS)),
        "interrupts": sum(1 for e in events if INTERRUPT_MARKER in e.text),
        "plan_mode_used": any(e.tool in ("EnterPlanMode", "ExitPlanMode") for e in tools),
        "tool_errors": sum(1 for r in results if r.is_error),
    }


def diff_stats(diff: str) -> dict:
    files = re.findall(r"^diff --git a/(\S+)", diff, re.M)
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return {"files_changed": files, "lines_added": added, "lines_removed": removed,
            "tests_changed": [f for f in files if "/tests/" in f]}


def _short(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f" ... [{len(text) - limit} chars cut]"


def render_log(events: list[Event], max_chars: int = 120_000) -> str:
    """Condensed, chronological transcript for the grader."""
    if not events:
        return "(empty transcript)"
    t0 = events[0].ts
    lines = []
    for e in events:
        stamp = f"[+{(e.ts - t0).total_seconds() / 60:5.1f}m]"
        if e.kind == "user_prompt":
            lines.append(f"\n{stamp} ENGINEER: {_short(e.text, 4000)}")
        elif e.kind == "assistant_text":
            lines.append(f"{stamp} AI: {_short(e.text, 1500)}")
        elif e.kind == "tool_use":
            inp = e.tool_input
            if e.tool == "Bash":
                detail = inp.get("command", "")
            elif e.tool in ("Edit", "MultiEdit"):
                detail = f"{inp.get('file_path', '')}: {_short(inp.get('old_string', ''), 300)} -> " \
                         f"{_short(inp.get('new_string', ''), 500)}"
            elif e.tool == "Write":
                detail = f"{inp.get('file_path', '')} ({len(str(inp.get('content', '')))} chars)"
            else:
                detail = inp
            lines.append(f"{stamp}   tool {e.tool}: {_short(detail, 800)}")
        elif e.kind == "tool_result":
            flag = " ERROR" if e.is_error else ""
            lines.append(f"{stamp}   result{flag}: {_short(e.text, 400)}")
        elif e.kind == "command":
            lines.append(f"{stamp}   (session command: {_short(e.text, 150)})")
    out = "\n".join(lines)
    if len(out) > max_chars:
        half = max_chars // 2
        out = out[:half] + "\n\n... [middle of transcript cut for length] ...\n\n" + out[-half:]
    return out


def format_metrics(m: dict) -> str:
    fv = m.get("final_verify") or {}
    rows = [
        ("Session length", f"{m['duration_minutes']} min"),
        ("Your prompts", f"{m['user_prompts']} (first prompt {m['first_prompt_chars']} chars)"),
        ("AI tool calls", f"{m['tool_calls']} ({m['edit_calls']} edits)"),
        ("Code runs before first edit", m["code_runs_before_first_edit"]),
        ("Code runs after last edit", m["code_runs_after_last_edit"]),
        ("Prompts asking for plan / RCA", m["prompts_asking_plan_or_rca"]),
        ("Prompts that challenged the AI", m["prompts_challenging_ai"]),
        ("Tool rejections / interrupts", f"{m['tool_rejections']} / {m['interrupts']}"),
        ("Plan mode used", m["plan_mode_used"]),
        ("Diff", f"+{m['lines_added']} -{m['lines_removed']} in {len(m['files_changed'])} files"),
        ("Tests changed", ", ".join(m["tests_changed"]) or "none"),
        ("Verify attempts", m["verify_attempts"]),
        ("Hidden checks", f"{fv.get('passed', '?')}/{fv.get('total', '?')}"),
    ]
    width = max(len(r[0]) for r in rows)
    return "Session metrics\n" + "\n".join(f"  {k:<{width}}  {v}" for k, v in rows)
