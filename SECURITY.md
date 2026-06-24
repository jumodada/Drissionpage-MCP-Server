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
