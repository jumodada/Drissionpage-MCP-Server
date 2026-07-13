# Security Policy

DrissionPage MCP runs a local browser automation server for MCP clients. Treat it as local automation tooling with access to pages, cookies, downloads, and files available to the browser profile it uses.

## Supported Versions

Security fixes target the latest released version. If a vulnerability affects older versions, the project will document the affected range in the advisory or release notes.

## Reporting a Vulnerability

Please report security issues privately before opening a public issue.

Send a report to the maintainer email listed in `pyproject.toml`, or use GitHub private vulnerability reporting if it is enabled for the repository.

Include:

- Affected version or commit.
- Operating system and Python version.
- Minimal reproduction steps.
- Impact and any known workarounds.
- Whether the issue requires a malicious website, malicious MCP prompt, or local access.

## Security Considerations

- MCP clients can ask this server to open websites and interact with pages.
- Browser automation may expose authenticated sessions in the configured browser profile.
- Screenshots, extracted text, form values, and opt-in network body/header captures can contain sensitive information.
- The server does not need external API credentials, but it can interact with any site reachable from the local machine.

## Safe Usage

- Use a dedicated browser profile (`DP_USER_DATA_PATH`) for automation when handling sensitive accounts; avoid reusing a real daily browsing profile unless you accept cookie/session exposure.
- Review MCP client prompts before allowing actions on authenticated or production systems.
- Avoid saving screenshots or page content to shared paths unless needed.
- Keep Chrome sandboxing enabled for normal desktop use; use `DP_NO_SANDBOX=1` only when Chromium cannot start inside a restricted container or root environment.
- Respect website terms of service, robots.txt, and rate limits.
- DrissionPage MCP is a fully autonomous general browser automation tool. Its detection, visual action, batch action, and observable polling primitives may be composed by users in authorized environments and technical research. The project does not recommend using them to bypass human-verification or anti-automation systems and does not guarantee that such systems can be completed.

## Optional Runtime Guardrails

The default behavior stays compatible with earlier local stdio releases: if no
policy variables are configured, the server can navigate to any absolute
`http://` or `https://` URL requested by the MCP client and can save screenshots
to requested local paths.

For stricter local operation, set these environment variables in the MCP client
configuration:

| Variable | Purpose |
| --- | --- |
| `DP_MCP_NAV_ALLOWLIST` | Comma-separated host names or URL prefixes. When set, navigation is allowlist-first. |
| `DP_MCP_NAV_BLOCKLIST` | Comma-separated host names or URL prefixes to reject. |
| `DP_MCP_BLOCK_PRIVATE_NETWORK` | Set to `1`, `true`, or `yes` to reject localhost, loopback, private, link-local, reserved, and multicast IP navigation. |
| `DP_MCP_SCREENSHOT_ROOT` | Restrict `page_screenshot.path` writes to this directory tree. |
| `DP_MCP_UPLOAD_ROOT` | Restrict `element_upload_file` inputs to existing files inside this directory tree. |
| `DP_USER_DATA_PATH` | Use a dedicated browser profile directory for MCP-owned sessions. Exposed only as configured/redacted in `drissionpage://session/config`. |

Example:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp",
      "env": {
        "DP_MCP_NAV_ALLOWLIST": "example.com,https://docs.example.com/app",
        "DP_MCP_BLOCK_PRIVATE_NETWORK": "1",
        "DP_MCP_SCREENSHOT_ROOT": "/tmp/drissionpage-mcp-screenshots",
        "DP_MCP_UPLOAD_ROOT": "/tmp/drissionpage-mcp-uploads"
      }
    }
  }
}
```

Policy denials return structured `POLICY_DENIED` errors. Navigation policy is
checked before browser initialization, so a denied URL does not start a browser
session.

`form_fill_preview` redacts field values by default and never submits forms. Network listener beta tools only observe packets; headers are opt-in/redacted and bodies are opt-in/bounded.

Runtime request throttling is not implemented for the current local stdio server
because this package is a single-user MCP server rather than a remote
multi-tenant service.
Users should still respect target-site rate limits. Add server-side throttling
before exposing this server through any remote transport.
