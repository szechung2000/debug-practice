# debug-practice

Practice debugging production-style structured-finance ETL with Claude Code, and
get scored on **how you work with the AI**, not only on whether the bug is fixed.

Each scenario is a self-contained ETL service of about 450-600 lines of Python
with a planted defect or inefficiency, realistic data, an incident ticket, and
visible tests that pass. Hidden checks and the answer key are encrypted, so
the AI in your session cannot read them.

## Scenarios

| ID | Scenario | Domain | Type | Level | Time box |
|---|---|---|---|---|---|
| 01 | CMBS remittance restatements | CMBS investor reporting | correctness | medium | 30 min |
| 02 | CLO compliance runtime | CLO collateral compliance | performance | medium | 40 min |
| 03 | RMBS prepayment speeds | Non-agency RMBS analytics | correctness | hard | 40 min |
| 04 | ABS incremental extract | Auto ABS loan-level data | correctness | medium | 35 min |
| 05 | Agency MBS cash forecast | Agency MBS / Treasury | correctness | easy | 20 min |
| 06 | CRT loan performance rerun | CAS / STACR loan-level data | correctness | medium | 30 min |

Do not read the source of a scenario before you start it. Start with the
ticket, as you would on call. Suggested order: 05, 01, 06, 04, 02, 03.

## Setup (once)

Requirements: Python 3.11+, git, Claude Code (`claude` on your PATH).

```bash
make setup && source .venv/bin/activate
make check-key          # test the answer-key passphrase
```

Keep the passphrase in your password manager. Do not put it in the repo, in a
CLAUDE.md, in a shell profile, or in an environment variable in the shell where
Claude Code runs: the AI could then read the answers.

## One practice round

```bash
make start S=01                     # 1. attempt branch + fresh data + incident ticket
cd scenarios/01-cmbs-remittance-restatements
claude                              # 2. work the incident with Claude Code
                                    #    exit Claude Code when you think you are done
cd ../.. && make verify S=01        # 3. hidden checks, pass/fail count only
make grade S=01                     # 4. scored review of the fix and the interaction
make reset S=01                     #    optional: restore the scenario for another try
```

Rules of the round:

- Run `make verify` and `make grade` yourself, in your own terminal. They ask
  for the passphrase, and the AI cannot answer that prompt.
- Each `verify` run is counted. Using it as a trial-and-error oracle lowers
  your score. Prove the fix inside the session instead.
- Work as you would in production: you can add a CLAUDE.md, ask for plans,
  write tests, query the data. All of it is evidence for the grader.
- Stay in one scenario folder per session. Start `claude` from that folder.

## How grading works

`make grade` does four things:

1. Finds the Claude Code transcripts of your attempt in
   `~/.claude/projects/` (sessions started in this repo after `make start`).
2. Computes interaction metrics: prompts, edits before and after code runs,
   challenges to the AI, rejected tool calls, plan-mode use, diff size, tests
   changed, verify attempts.
3. Asks you to explain the root cause in your own words.
4. Sends the rubric, the answer key, the metrics, your diff, your explanation
   and the condensed transcript to a fresh `claude -p` process (outside the
   repo), which writes a scored review with rewritten example prompts.

Score: 40 points outcome (root cause, fix quality) + 60 points interaction
(framing, investigation, verification, steering, efficiency, ownership).
See [evaluation/RUBRIC.md](evaluation/RUBRIC.md).

Reports, metrics and session state are written to
`~/.debug-practice/debug-practice/`, outside the repo. `make history` shows
your scores over time. Use `--no-llm` to only write the grading prompt (you can
paste it into a new Claude chat), and `--transcript FILE` to choose transcripts.

## Repository layout

```
scenarios/NN-name/
  INCIDENT.md        the ticket: symptom, impact, what on-call tried
  README.md          service overview and run commands
  scenario.json      metadata used by the tools
  src/<package>/     the ETL service (the code under investigation)
  data/generate.py   deterministic data generator ("production" copy)
  tests/             visible tests (they pass; they do not cover the defect)
answer-key/bundle.enc  encrypted: root causes, decoys, hidden checks, reference patches
evaluation/          rubric and grader prompt
tools/               practice driver, transcript parser, key vault
```

## Adding or editing scenarios

```bash
python tools/keyvault.py unpack --out ~/dp-answer-key     # outside the repo
# edit ~/dp-answer-key/<scenario>/ANSWER.md, hidden_tests/, reference.patch
python tools/keyvault.py pack --src ~/dp-answer-key
rm -rf ~/dp-answer-key
```

A new scenario needs `scenario.json`, `INCIDENT.md`, `src/`, `data/generate.py`,
`tests/`, and an answer-key folder with the same name that holds `ANSWER.md`,
`hidden_tests/test_*.py` and `reference.patch`. Hidden tests get the scenario
path in `SCENARIO_DIR` and import the scenario package from `src/`.

Do not open the answer key or the reference patches for scenarios you have not
done yet. Do not read the commit history of a scenario before you attempt it.
