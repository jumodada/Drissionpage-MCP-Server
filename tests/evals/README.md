# DrissionMCP evals

Run:

```bash
python -m pytest tests/evals -q
```

These tests are deterministic, local, and do not require public internet access.
Browser-required scenarios may skip only when Chrome/Chromium is unavailable.

`test_eval_task_completion.py` defines the deterministic 0.7 workload fixture
catalog and side-effect evidence foundation. The eight workload IDs remain
separate from public-tool orchestration so fixture contracts stay executable
while the new 0.7 tools are introduced incrementally.
