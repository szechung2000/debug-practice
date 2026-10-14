# Evaluation rubric

The grader scores two things:

1. **Outcome (40 points).** Did you find the real root cause and fix it correctly?
2. **Interaction (60 points).** How did you work with the AI to get there?

The interaction score is the main purpose of this repo. A correct fix that you
got by accepting the first AI suggestion without checking it scores lower than
a partial fix that you reached with sound, evidence-driven steering.

Each dimension gets a level from 0 to 4. Points = level / 4 x weight.

## A. Outcome (40)

| Dimension | Weight | 4 (strong) | 2 (partial) | 0 (absent) |
|---|---|---|---|---|
| A1. Root cause | 20 | You name the exact mechanism and location. Your own explanation matches the answer key. | You fix the symptom, or you name the right area but the wrong mechanism. | Wrong cause, or no cause stated. |
| A2. Fix quality | 20 | Minimal, correct fix. All hidden checks pass. A regression test covers the defect. No unrelated changes. | Fix works but is broad, has side effects, or has no test. | Fix fails hidden checks, or hides the problem (try/except, skip rows, change tests to pass). |

## B. Interaction (60)

| Dimension | Weight | What the grader looks for |
|---|---|---|
| B1. Problem framing | 10 | Your first prompts give the AI the symptom, the impact, the expected behaviour, and the data or command that shows the problem. You state constraints (for example "do not change the output schema"). Weak: "there's a bug, fix it". |
| B2. Investigation strategy | 10 | You ask for hypotheses and a reproduction before any edit. You direct the AI to evidence: logs, data, counts, a failing test. You use plan mode or say "do not edit yet". Weak: the first AI action is an edit. |
| B3. Verification and skepticism | 15 | You ask the AI to prove its claims with output, not with reasoning only. You make it show the failure before the fix and the pass after the fix. You catch confident but wrong claims and decoys. You do not treat the hidden checks as a test oracle. Weak: you accept "this should fix it". |
| B4. Steering and scope control | 10 | You keep the change small. You reject unrelated refactors, new dependencies and edits to existing tests. You redirect the AI fast when it goes down a wrong path. |
| B5. Efficiency | 5 | Turns and time match the difficulty. No loops of "try this, it still fails". Prompts are specific enough that the AI does not have to guess. |
| B6. Understanding and ownership | 10 | You can explain the mechanism in your own words. You ask the AI to explain why, not only what. You think about blast radius: other periods, other deals, backfill, downstream consumers. |

## Anti-patterns (each one lowers the related dimension)

- You accept the first fix without a reproduction (B3).
- The AI edits or deletes existing tests to make them pass, and you allow it (A2, B4).
- The AI rewrites a whole module for a one-line defect (B4).
- You run `verify` many times to find the answer by trial (B3, B5).
- You paste the error with no context and say "fix" (B1).
- You let the AI add broad `try/except`, row filters or retries that hide the defect (A2).
- You approve destructive commands on the "production" store without a reason (B4).

## Strong signals

- "Before you change anything, give me three hypotheses and the evidence that would confirm or reject each."
- "Write a failing test that reproduces the incident first."
- "Show me the rows that are wrong."
- "You said X. Run it and show me."
- "Which other periods or deals does this affect, and what is the backfill plan?"
