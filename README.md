# agent-harness-starter

A minimal, dependency-free harness for running coding agents safely: **ticket → spec → agent run → quality gates → human review → release.**

The idea: the harness around an agent (the spec it gets, the gates its output must pass, and the review step) matters as much as the model. This repo is a small, readable starting point for that pattern.

## What it does
- **Spec first.** Tickets without acceptance criteria are rejected at intake instead of being guessed at.
- **Pluggable agent.** Any `Callable[[Spec], ChangeSet]` works: an LLM client, a script, or the bundled `stub_agent`.
- **Quality gates.** Non-empty change, tests pass, no obvious secrets, scope limit. Add your own in one function.
- **Human in the loop.** Nothing reaches `release` without an explicit reviewer approval. The default is to wait.
- **Audit trail.** Every stage is logged with a timestamp in a `RunRecord`.

## Quick start
```bash
python -m harness examples/tickets/T-1.json            # stops at awaiting-review
python -m harness examples/tickets/T-1.json --approve  # reaches release
python -m harness examples/tickets/T-2.json            # rejected: no acceptance criteria
python -m unittest -v
```
Requires Python 3.10+. No dependencies.

## Adding a gate
```python
def gate_has_tests(spec, cs):
    ok = any(p.startswith("tests/") for p in cs.files)
    return GateResult("has-tests", ok, "" if ok else "no test files changed")

run(ticket, my_agent, gates=DEFAULT_GATES + [gate_has_tests], reviewer=my_review)
```

## License
MIT
