# DrissionPage MCP Skills

DrissionPage MCP keeps browser primitives in the MCP server and publishes
procedural guidance as Skills. A Skill is a Markdown procedure that tells an
MCP client how to combine `tools/list`, typed inputs, fresh observations, and
postcondition checks for one bounded class of work.

## Where Skills live

The repository contains example Skills under `skills/<name>/SKILL.md`. They are
source documentation, not Python modules: the wheel and sdist intentionally do
not include them. The MCP server exposes discovery metadata through
`drissionpage://skills/catalog`; clients can use the listed `source_url` values
to inspect the examples from the repository or an external Skills catalog.

## Example catalog

| Skill | Use it for | Important boundary |
| --- | --- | --- |
| `cross-origin-iframe-probe` | Decide whether an iframe is DOM-reachable and choose frame, coordinate, or keyboard fallbacks | Cross-origin documents cannot be read through the parent DOM |
| `turnstile-testing` | Authorized Turnstile test fixtures and parent-page verification | Never bypass production challenges or treat a safety page as a selector bug |
| `xiaohongshu-content-research` | Bounded, read-only note research and the local `social-notes` fixture | Stop on robots, login, captcha, safety restriction, or rate-limit boundaries |

## Skill contract

Every Skill should:

1. Declare a stable `name` and a one-sentence `description` in YAML frontmatter.
2. State authorization, privacy, rate, login, captcha, and submission boundaries.
3. Compose existing atomic tools instead of inventing tool names or hidden APIs.
4. Re-observe after navigation and consequential actions; verify explicit
   postconditions instead of trusting a click result.
5. Describe unsupported cases and a stop condition.
6. Prefer deterministic local fixtures for repeatable tests.

Skills must not add browser capabilities, silently change safety policy, echo
secrets, or claim to defeat anti-bot systems. Site-specific business decisions
belong in the host application and require the operator's authorization.

## Using a repository example

From a checkout, open the requested file and provide it to the MCP host as
Skill context. The Skill itself does not run a browser. The host performs the
tool calls against the connected DrissionPage MCP server:

```text
Repository: https://github.com/jumodada/Drissionpage-MCP-Server
Skill: skills/xiaohongshu-content-research/SKILL.md
Core server: drissionpage-mcp 0.8.2
```

For release validation, install a built wheel or sdist in a clean environment,
then run the local fixture using that interpreter:

```bash
DP_HEADLESS=1 \
python playground/run_mcp_lab.py \
  --case social-notes \
  --command /tmp/clean-venv/bin/python \
  --json \
  --args -I -m drissionpage_mcp.cli --log-level ERROR
```

`-I` prevents the server subprocess from importing a repository checkout ahead
of the installed release package. This validates the Skill's tool sequence
without contacting Xiaohongshu.
