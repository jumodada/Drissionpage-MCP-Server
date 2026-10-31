# DrissionMCP evals

Run:

```bash
python -m pytest tests/evals -q
```

These tests are deterministic, local, and do not require public internet access.
Browser-required scenarios may skip only when Chrome/Chromium is unavailable.

`test_eval_task_completion.py` defines the deterministic 0.7 workload fixture
catalog and side-effect evidence foundation. The executable public-tool
benchmark is available as:

```bash
DP_HEADLESS=1 DP_NO_SANDBOX=1 DP_MCP_REQUIRE_BROWSER=1 \
python -m tests.evals.task_completion_benchmark \
  --iterations 10 \
  --output benchmark-results/0.9.0-task-completion.json
```

It starts one isolated browser per iteration, runs W01-W08 through the MCP
server path, records tool calls, runtime evidence, and observed fixture
side-effect counters, and fails unless every workload reaches 9/10 with zero
duplicate side effects. When any run fails, the console output includes a
bounded `failed_runs` list so CI diagnosis does not depend on artifact access.

With `--output`, the command writes
`benchmark-results/0.9.0-task-completion.json`; omit that option for stdout-only
local validation. On 2026-10-21, the 0.9.0 candidate completed W01-W08 80/80
with zero duplicate side effects and the local challenge surfaces 50/50.
Hosted Ubuntu artifacts and the remaining platform jobs are separate release
gates. See [the changelog](../../CHANGELOG.md#090---2026-10-20) for the environment
and package comparison results.

The generic challenge-surface benchmark is local and deterministic:

```bash
DP_HEADLESS=1 DP_NO_SANDBOX=1 DP_MCP_REQUIRE_BROWSER=1 \
python -m tests.evals.challenge_surface_benchmark --iterations 10
```

The snapshot-search comparison runs two fixed local retrieval workloads 20
times against isolated 0.8.8 baseline and candidate wheel environments through
real stdio MCP. It counts model-visible response characters as compact strict
JSON `structuredContent` plus every text content mirror. CI builds the baseline
wheel from commit `30e8adf`, builds the candidate wheel from the checked-out
tree, runs each server from a temporary working directory without forcing a
profile-path override, and does not resolve either application package from PyPI. The gate
requires 20/20 completion for both packages, no candidate tool-call increase,
matching Python/MCP/DrissionPage/Chrome evidence, and at least 30% lower P50
characters for both workloads:

```bash
python -m tests.evals.snapshot_search_comparison \
  --baseline-python /path/to/baseline-venv/bin/python \
  --baseline-artifact /path/to/drissionpage_mcp-0.8.8.whl \
  --candidate-python /path/to/candidate-venv/bin/python \
  --candidate-artifact /path/to/drissionpage_mcp-0.9.0.whl \
  --iterations 20
```

The comparison prints its evidence report to stdout; CI does not create or
upload a benchmark JSON file.

The official Turnstile dummy-key benchmark loads Cloudflare's test script and
therefore requires explicit external-network opt-in:

```bash
DP_HEADLESS=1 DP_NO_SANDBOX=1 DP_MCP_REQUIRE_BROWSER=1 \
python -m tests.evals.turnstile_testkey_benchmark \
  --iterations 10 --allow-external
```
