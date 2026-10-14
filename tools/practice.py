"""Practice session driver.

  python tools/practice.py list
  python tools/practice.py start  01        # new attempt branch, fresh data, show incident
  python tools/practice.py verify 01        # hidden checks (asks for passphrase)
  python tools/practice.py grade  01        # score the fix and your AI interaction
  python tools/practice.py reset  01        # put the scenario back to its original state
  python tools/practice.py history          # scores of earlier attempts

Run these commands yourself, in your own terminal. Do not ask the AI to run
`verify` or `grade`: both commands need the passphrase, and the grader counts
each `verify` call.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyvault  # noqa: E402
import transcript as tx  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = REPO_ROOT / "scenarios"
# Session state and grading reports live outside the repo, so an AI session
# working in the repo does not read earlier answer keys or reports.
STATE = Path(os.environ.get("DEBUG_PRACTICE_HOME", Path.home() / ".debug-practice")) / REPO_ROOT.name
SESSIONS = STATE / "sessions"
REPORTS = STATE / "reports"
EVAL = REPO_ROOT / "evaluation"


# --------------------------------------------------------------------------- helpers
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def git(*args: str, check: bool = True) -> str:
    res = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{res.stderr.strip()}")
    return res.stdout.strip()


def find_scenario(ident: str) -> Path:
    matches = sorted(p for p in SCENARIOS.iterdir() if p.is_dir() and p.name.startswith(ident))
    if len(matches) != 1:
        names = ", ".join(p.name for p in SCENARIOS.iterdir() if p.is_dir())
        raise SystemExit(f"scenario '{ident}' does not match exactly one of: {names}")
    return matches[0]


def scenario_meta(path: Path) -> dict:
    return json.loads((path / "scenario.json").read_text())


def latest_session(scenario: Path) -> tuple[Path, dict]:
    files = sorted(SESSIONS.glob(f"{scenario.name}__*.json"))
    if not files:
        raise SystemExit(f"no attempt found for {scenario.name}; run `start` first")
    return files[-1], json.loads(files[-1].read_text())


def save_session(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def run_generator(scenario: Path) -> None:
    gen = scenario / "data" / "generate.py"
    if gen.exists():
        subprocess.run([sys.executable, str(gen)], cwd=scenario, check=True)


# --------------------------------------------------------------------------- commands
def cmd_list(_args) -> int:
    print(f"{'id':<4} {'scenario':<34} {'type':<12} {'level':<8} time box")
    for path in sorted(p for p in SCENARIOS.iterdir() if p.is_dir()):
        m = scenario_meta(path)
        print(f"{m['id']:<4} {path.name:<34} {m['type']:<12} {m['difficulty']:<8} {m['timebox_minutes']} min")
    return 0


def cmd_start(args) -> int:
    scenario = find_scenario(args.scenario)
    if git("status", "--porcelain", "--", str(scenario)):
        raise SystemExit(f"{scenario.name} has local changes. Run `reset {args.scenario}` first.")
    stamp = now_utc().strftime("%Y%m%d-%H%M%S")
    branch = f"attempt/{scenario.name}-{stamp}"
    base = git("rev-parse", "HEAD")
    git("switch", "-c", branch)
    run_generator(scenario)
    SESSIONS.mkdir(parents=True, exist_ok=True)
    session = {
        "scenario": scenario.name,
        "branch": branch,
        "base_sha": base,
        "started_at": now_utc().isoformat(),
        "verify_attempts": [],
    }
    save_session(SESSIONS / f"{scenario.name}__{stamp}.json", session)
    meta = scenario_meta(scenario)
    print(f"\nAttempt branch: {branch}")
    print(f"Time box: {meta['timebox_minutes']} minutes. The clock starts now.\n")
    print((scenario / "INCIDENT.md").read_text())
    print("Next steps:")
    print(f"  cd {scenario.relative_to(REPO_ROOT)} && claude")
    print(f"  When you are done, exit Claude Code and run: make verify S={meta['id']}")
    return 0


def cmd_verify(args) -> int:
    scenario = find_scenario(args.scenario)
    session_path, session = latest_session(scenario)
    meta = scenario_meta(scenario)
    with tempfile.TemporaryDirectory(prefix="dp-verify-") as tmp:
        key = keyvault.load_scenario_key(scenario.name, Path(tmp) / "key")
        result = run_hidden_tests(scenario, key, verbose=args.details)
    session["verify_attempts"].append({"at": now_utc().isoformat(), **result["summary"]})
    save_session(session_path, session)
    s = result["summary"]
    print(f"\n{meta['id']} {scenario.name}: {s['passed']}/{s['total']} hidden checks pass "
          f"(verify attempt #{len(session['verify_attempts'])})")
    if args.details:
        print(result["output"])
    elif s["passed"] < s["total"]:
        print("Some checks fail. Use --details to see them (this spoils the answer).")
    return 0 if s["passed"] == s["total"] else 1


def run_hidden_tests(scenario: Path, key_dir: Path, verbose: bool) -> dict:
    tests = key_dir / "hidden_tests"
    work = Path(tempfile.mkdtemp(prefix="dp-hidden-"))
    try:
        shutil.copytree(tests, work / "hidden_tests")
        report = work / "report.json"
        env = {**os.environ, "SCENARIO_DIR": str(scenario),
               "PYTHONPATH": str(scenario / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(work),
               str(work / "hidden_tests"), "-o", "console_output_style=classic"]
        if not verbose:
            cmd += ["--tb=no", "-rN"]
        proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=900)
        out = proc.stdout + proc.stderr
        passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
        failed = sum(int(x) for x in re.findall(r"(\d+) (?:failed|error)", out))
        report.write_text(out)
        return {"summary": {"passed": passed, "total": passed + failed}, "output": out}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def cmd_reset(args) -> int:
    scenario = find_scenario(args.scenario)
    ref = args.ref or "main"
    git("checkout", ref, "--", str(scenario))
    git("clean", "-fdq", "--", str(scenario))
    run_generator(scenario)
    print(f"{scenario.name} restored from {ref}.")
    return 0


def cmd_grade(args) -> int:
    scenario = find_scenario(args.scenario)
    session_path, session = latest_session(scenario)
    meta = scenario_meta(scenario)
    started = datetime.fromisoformat(session["started_at"])
    out_dir = REPORTS / session_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [Path(p) for p in args.transcript] if args.transcript else tx.find_transcripts(REPO_ROOT, started)
    if not files:
        print("No Claude Code transcript found for this attempt. Pass --transcript PATH.", file=sys.stderr)
        return 2
    events = tx.load_events(files, since=started)
    metrics = tx.compute_metrics(events)
    metrics["verify_attempts"] = len(session["verify_attempts"])
    metrics["final_verify"] = session["verify_attempts"][-1] if session["verify_attempts"] else None
    diff = git("diff", session["base_sha"], "--", str(scenario), check=False)
    metrics.update(tx.diff_stats(diff))

    explanation = ""
    if not args.no_explain and sys.stdin.isatty():
        print("In 2-5 sentences and in your own words: what was the root cause, and why does your fix work?")
        print("(End with an empty line.)")
        lines = []
        while (line := input()) != "":
            lines.append(line)
        explanation = "\n".join(lines)

    with tempfile.TemporaryDirectory(prefix="dp-grade-") as tmp:
        key = keyvault.load_scenario_key(scenario.name, Path(tmp) / "key")
        answer = (key / "ANSWER.md").read_text()
        if not session["verify_attempts"]:
            print("No verify run yet; running hidden checks now (not counted as an attempt).")
            metrics["final_verify"] = run_hidden_tests(scenario, key, verbose=False)["summary"]

    prompt = build_grading_prompt(meta, answer, metrics, diff, explanation, tx.render_log(events))
    (out_dir / "grading_prompt.md").write_text(prompt)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("\n" + tx.format_metrics(metrics))

    if args.no_llm or not shutil.which("claude"):
        print(f"\nGrading prompt written to {out_dir / 'grading_prompt.md'}.")
        print("Paste it into a NEW Claude chat (not the practice session) to get the scored review.")
        return 0
    print("\nAsking a fresh Claude instance to grade the session (1-3 minutes)...")
    with tempfile.TemporaryDirectory(prefix="dp-grader-") as cwd:
        proc = subprocess.run(["claude", "-p", "Grade this debugging session. Follow the instructions in the input exactly."],
                              input=prompt, capture_output=True, text=True, cwd=cwd, timeout=900)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"Grader failed. Prompt is at {out_dir / 'grading_prompt.md'}.")
        return 1
    report = proc.stdout
    (out_dir / "report.md").write_text(report)
    print(report)
    scores = extract_scores(report)
    if scores:
        with (STATE / "history.jsonl").open("a") as fh:
            fh.write(json.dumps({"attempt": session_path.stem, "scenario": scenario.name,
                                 "graded_at": now_utc().isoformat(), **scores}) + "\n")
    print(f"\nReport saved to {out_dir / 'report.md'}")
    return 0


def build_grading_prompt(meta, answer, metrics, diff, explanation, log) -> str:
    template = (EVAL / "grader_prompt.md").read_text()
    rubric = (EVAL / "RUBRIC.md").read_text()
    if len(diff) > 40_000:
        diff = diff[:40_000] + "\n... [diff truncated]"
    return (template
            .replace("{{RUBRIC}}", rubric)
            .replace("{{SCENARIO}}", json.dumps(meta, indent=2))
            .replace("{{ANSWER_KEY}}", answer)
            .replace("{{METRICS}}", json.dumps(metrics, indent=2))
            .replace("{{DIFF}}", diff or "(no changes)")
            .replace("{{EXPLANATION}}", explanation or "(the engineer gave no explanation)")
            .replace("{{TRANSCRIPT}}", log))


def extract_scores(report: str) -> dict | None:
    m = re.search(r"```json\s*(\{.*?\})\s*```", report, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def cmd_history(_args) -> int:
    path = STATE / "history.jsonl"
    if not path.exists():
        print("No graded attempts yet.")
        return 0
    print(f"{'graded':<17} {'scenario':<34} {'outcome':>7} {'interaction':>11} {'total':>5}")
    for line in path.read_text().splitlines():
        r = json.loads(line)
        print(f"{r['graded_at'][:16]:<17} {r['scenario']:<34} {r.get('outcome_score', '-'):>7} "
              f"{r.get('interaction_score', '-'):>11} {r.get('total_score', '-'):>5}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("history").set_defaults(fn=cmd_history)
    p = sub.add_parser("start"); p.add_argument("scenario"); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("verify"); p.add_argument("scenario")
    p.add_argument("--details", action="store_true", help="show failing check output (spoils the answer)")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("reset"); p.add_argument("scenario"); p.add_argument("--ref")
    p.set_defaults(fn=cmd_reset)
    p = sub.add_parser("grade"); p.add_argument("scenario")
    p.add_argument("--transcript", nargs="*", help="Claude Code session .jsonl file(s)")
    p.add_argument("--no-llm", action="store_true", help="only write the grading prompt")
    p.add_argument("--no-explain", action="store_true", help="skip the root-cause explanation prompt")
    p.set_defaults(fn=cmd_grade)
    args = ap.parse_args()
    try:
        return args.fn(args)
    except keyvault.VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
