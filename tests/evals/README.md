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
  --output benchmark-results/0.7.1-task-completion.json
```

It starts one isolated browser per iteration, runs W01-W08 through the MCP
server path, records tool calls, runtime evidence, and observed fixture
side-effect counters, and fails unless every workload reaches 9/10 with zero
<<<<<<< HEAD
duplicate side effects. When any run fails, the console output includes a
bounded `failed_runs` list so CI diagnosis does not depend on artifact access.
=======
duplicate side effects.
>>>>>>> a892045afa29a9c1e7751cde256599015e912153

The latest committed local summary is in
[`docs/0.7.1-release-evidence.md`](../../docs/0.7.1-release-evidence.md). The
Ubuntu CI JSON artifact remains the release gate for the Linux browser matrix.
