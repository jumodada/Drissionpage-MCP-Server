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
- Screenshots and extracted text can contain sensitive information.
- The server does not need external API credentials, but it can interact with any site reachable from the local machine.

## Safe Usage

- Use a dedicated browser profile for automation when handling sensitive accounts.
- Review MCP client prompts before allowing actions on authenticated or production systems.
- Avoid saving screenshots or page content to shared paths unless needed.
- Respect website terms of service, robots.txt, and rate limits.

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

Example:

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp",
      "env": {
        "DP_MCP_NAV_ALLOWLIST": "example.com,https://docs.example.com/app",
        "DP_MCP_BLOCK_PRIVATE_NETWORK": "1",
        "DP_MCP_SCREENSHOT_ROOT": "/tmp/drissionpage-mcp-screenshots"
      }
    }
  }
}
```

Policy denials return structured `POLICY_DENIED` errors. Navigation policy is
checked before browser initialization, so a denied URL does not start a browser
session.

Runtime request throttling is not implemented in 0.3.2 because this package is
a local stdio, single-user MCP server rather than a remote multi-tenant service.
Users should still respect target-site rate limits. Add server-side throttling
before exposing this server through any remote transport.
