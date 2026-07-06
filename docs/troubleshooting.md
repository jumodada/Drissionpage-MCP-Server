# Troubleshooting

Use this guide when the MCP server does not start, tools do not appear, or browser automation fails.

## First Checks

Run these commands from a shell:

```bash
python -m pip install -U drissionpage-mcp
drissionpage-mcp --version
drissionpage-mcp doctor
drissionpage-mcp doctor --launch-browser
python playground/run_mcp_lab.py --case registry
```

Expected result:

- The version command prints the installed `drissionpage-mcp` version.
- `drissionpage-mcp doctor` reports Python, package, browser, and environment diagnostics.
- `drissionpage-mcp doctor --launch-browser` proves Chrome/Chromium can actually start.
- `playground/run_mcp_lab.py --case registry` proves the stdio MCP registry loads successfully.

For a source checkout, install development dependencies first:

```bash
python -m pip install -e ".[dev]"
python playground/run_mcp_lab.py --case registry
```

## MCP Client Cannot Find the Server

Check the MCP client configuration uses the installed command.

For Codex CLI/IDE, `~/.codex/config.toml` or a trusted project `.codex/config.toml` should contain:

```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

For JSON MCP clients, configure:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

Then verify:

- Codex: run `codex mcp list`; in the TUI, run `/mcp`.
- JSON clients: restart the MCP client after editing JSON.
- Confirm the TOML or JSON syntax is valid.
- Confirm `drissionpage-mcp --version` works in the same shell environment used by the client.
- For source installs, prefer `python -m drissionpage_mcp.cli` with an absolute `cwd`.
- For GUI clients that do not inherit your shell `PATH` or virtualenv, use an
  absolute Python executable:

  ```json
  {
    "mcpServers": {
      "drissionpage": {
        "command": "/absolute/path/to/python",
        "args": ["-m", "drissionpage_mcp.cli"]
      }
    }
  }
  ```

- If `pip` cannot find a newly published version, your package mirror may be stale; retry with `python -m pip install -U --index-url https://pypi.org/simple drissionpage-mcp`.

## Tools Do Not Appear

1. Run diagnostics and, if needed, debug logging:

   ```bash
   drissionpage-mcp doctor
   python -m drissionpage_mcp.cli --log-level DEBUG
   ```

2. Check the MCP client logs for startup, TOML, or JSON configuration errors.
3. Confirm the package imports correctly:

   ```bash
   python -c "from drissionpage_mcp.tools import get_all_tools; print(len(get_all_tools()))"
   ```

The current 0.5.5 tool registry should load 46 tools.

## Browser Does Not Start

DrissionPage requires a local Chrome or Chromium browser. Start with the launch
check because it catches missing binaries, sandbox failures, and no-display
remote environments:

```bash
drissionpage-mcp doctor --launch-browser
```

Check common browser commands:

```bash
which google-chrome || true
which chromium || true
which chromium-browser || true
```

On Windows, confirm Chrome or Chromium is installed and available to DrissionPage. If you use a custom browser path, configure it through your local environment or DrissionPage settings.

For SSH, Docker, Codespaces, CI, or other no-GUI environments, run headless and
set the browser path explicitly in your MCP client configuration:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp",
      "env": {
        "CHROME_PATH": "/usr/bin/chromium",
        "DP_HEADLESS": "1"
      }
    }
  }
}
```

Chrome sandboxing stays enabled by default. If Chromium is running as root or
inside a restricted container and `doctor --launch-browser` reports a sandbox
startup error, add `DP_NO_SANDBOX=1` only for that environment.

## Navigation or Element Actions Fail

Common causes:

- The page did not finish loading before the action.
- The selector does not match the page.
- The element is inside an iframe, shadow root, or dynamic UI state not yet exposed to DrissionPage.
- The site blocks automation or requires authentication.

Useful recovery steps:

1. Check `error.details.hints` in the `### JSON_RESULT` block. The server now
   returns structured next steps for common failures.
2. Use `page_snapshot` to inspect the current page outline and recommended
   selectors without pulling full-page HTML.
3. Use `element_find_all` with a broader selector to discover repeated cards,
   table rows, links, or similar candidate elements.
4. Use `wait_until` for dynamic conditions such as `clickable`, `hidden`,
   `stable`, text updates, or URL transitions.
5. Use `observe=true` on `page_navigate`, `element_click`, or `element_type`
   when you need a compact before/after change summary.
6. Use `page_console_logs` or inspect the `console_errors_added`,
   `console_warnings_added`, and `new_console_messages` fields from
   `observe=true` when an action silently fails on the page.
7. Use `wait_for_element` before simple `element_click` or `element_type` calls.
8. Increase the per-tool timeout where supported. `element_find` defaults to 3 seconds for fast feedback; explicit wait tools keep longer waits.
9. Re-check selectors in the browser devtools. Bare selectors are treated as CSS; use `text:Submit` for text matching and explicit `tag:`, `css:`, `xpath:`, or `@name=value` forms when needed.
10. If the element may be inside an iframe, inspect with `frame_list`,
   `frame_snapshot`, and `frame_find` before retrying the action.
11. If the element may be inside an open shadow root, inspect with `shadow_find`
   or `shadow_find_all`.

## Screenshots Fail

If `page_screenshot` fails:

- Confirm a page is open with `page_get_url`.
- Try a viewport screenshot before a full-page screenshot.
- Check whether the browser is still connected.

If `page_screenshot_save` fails:

- Set `DP_MCP_SCREENSHOT_ROOT` to the directory where screenshots may be written.
- Save only to a path inside that directory.

## File Uploads Fail

`element_upload_file` is intentionally root-gated:

- Set `DP_MCP_UPLOAD_ROOT` to the directory containing files that MCP may upload.
- Pass paths that resolve inside that directory.
- Confirm each path exists and is a regular file.
- Successful responses return file names only, not absolute paths.

## Reporting Issues

When filing an issue, include:

- OS and Python version.
- `drissionpage-mcp --version` output.
- Browser name and version.
- MCP client name and version.
- Minimal MCP config with secrets removed.
- Debug logs from `python -m drissionpage_mcp.cli --log-level DEBUG`.
