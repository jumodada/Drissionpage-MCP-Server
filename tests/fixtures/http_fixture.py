"""Local deterministic HTTP fixture app for browser and protocol tests."""

from __future__ import annotations

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Iterator
from urllib.parse import parse_qs, urlparse


class FixtureRequestHandler(BaseHTTPRequestHandler):
    """Serve deterministic pages without external network access."""

    server_version = "DrissionMCPTestFixture/1.0"

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if parsed.path == "/api/echo.json":
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8") if length else ""
            payload = {
                "ok": True,
                "method": "POST",
                "query": parse_qs(parsed.query),
                "body": body,
            }
            self._send_json(payload)
            return
        self._send_text("not found", status=404)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Home</title></head>
                  <body>
                    <main id="app" data-page="home">
                      <h1>DrissionMCP Fixture</h1>
                      <a id="form-link" href="/form">Form</a>
                      <a id="dynamic-link" href="/dynamic">Dynamic</a>
                      <a id="new-tab-link" href="/new-tab" target="_blank">Open New Tab</a>
                      <iframe id="fixture-frame" src="/iframe" title="Fixture Frame"></iframe>
                    </main>
                  </body>
                </html>
                """
            )
            return

        if path == "/form":
            submitted = parse_qs(parsed.query).get("name", [""])[0]
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Form</title></head>
                  <body>
                    <form id="fixture-form" method="get" action="/form">
                      <label for="name">Name</label>
                      <input id="name" name="name" value="{submitted}" />
                      <label for="secret">Secret</label>
                      <input id="secret" name="secret" type="password" value="fixture-secret" />
                      <button id="submit" type="submit">Submit</button>
                    </form>
                    <output id="submitted">{submitted}</output>
                  </body>
                </html>
                """.format(
                    submitted=_escape_html(submitted)
                )
            )
            return

        if path == "/upload":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Upload</title></head>
                  <body>
                    <main id="upload-workflow">
                      <h1>Upload Workflow</h1>
                      <label for="upload">Upload file</label>
                      <input id="upload" name="upload" type="file" />
                      <output id="upload-name">none</output>
                    </main>
                    <script>
                      document.getElementById('upload').addEventListener('change', function () {
                        document.getElementById('upload-name').textContent =
                          this.files.length ? this.files[0].name : 'none';
                      });
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/interactions":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head>
                    <title>Fixture Interactions</title>
                    <style>
                      body { min-height: 1800px; }
                      #deep-target { margin-top: 1200px; }
                      #hover-target { display: inline-block; padding: 8px; }
                    </style>
                  </head>
                  <body>
                    <main id="interaction-workflow">
                      <h1>Interaction Workflow</h1>
                      <label for="mode">Mode</label>
                      <select id="mode" name="mode">
                        <option value="basic">Basic</option>
                        <option value="advanced">Advanced</option>
                      </select>
                      <label for="agree">Agree</label>
                      <input id="agree" name="agree" type="checkbox" />
                      <label for="keyboard-input">Keyboard</label>
                      <input id="keyboard-input" name="keyboard" value="" />
                      <button id="hover-target" type="button">Hover me</button>
                      <output id="hover-status">waiting</output>
                      <section id="deep-target">Deep target</section>
                    </main>
                    <script>
                      document.getElementById('hover-target').addEventListener('mouseover', function () {
                        document.getElementById('hover-status').textContent = 'hovered';
                      });
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/shadow":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Shadow</title></head>
                  <body>
                    <main id="shadow-workflow">
                      <h1>Shadow Workflow</h1>
                      <div id="shadow-host"></div>
                    </main>
                    <script>
                      const host = document.getElementById('shadow-host');
                      const root = host.attachShadow({mode: 'open'});
                      root.innerHTML = `
                        <section id="shadow-root">
                          <button id="shadow-button" type="button">Shadow Action</button>
                          <ul>
                            <li id="shadow-alpha" class="shadow-item">Shadow Alpha</li>
                            <li id="shadow-beta" class="shadow-item">Shadow Beta</li>
                          </ul>
                        </section>
                      `;
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/storage":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Storage</title></head>
                  <body>
                    <main id="storage-workflow">
                      <h1>Storage Workflow</h1>
                      <output id="storage-status">ready</output>
                    </main>
                    <script>
                      document.cookie = 'fixture_cookie=fixture; path=/; SameSite=Lax';
                      localStorage.setItem('fixture-local', 'local-value');
                      sessionStorage.setItem('fixture-session', 'session-value');
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/dynamic":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Dynamic</title></head>
                  <body>
                    <div id="dynamic-root">loading</div>
                    <script>
                      window.setTimeout(function () {
                        var node = document.createElement('p');
                        node.id = 'dynamic-ready';
                        node.textContent = 'dynamic content ready';
                        document.getElementById('dynamic-root').appendChild(node);
                      }, 50);
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/observable":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Observable</title></head>
                  <body>
                    <main id="observable-root">
                      <h1>Observable Workflow</h1>
                      <div id="spinner">Loading...</div>
                      <output id="status" role="status">waiting</output>
                      <button id="delayed" type="button" disabled>Save</button>
                    </main>
                    <script>
                      window.setTimeout(function () {
                        document.getElementById('delayed').disabled = false;
                        document.getElementById('spinner').remove();
                        document.getElementById('status').textContent = 'ready';
                      }, 80);
                      document.getElementById('delayed').addEventListener('click', function () {
                        document.title = 'Fixture Observable Saved';
                        document.getElementById('status').textContent = 'saved successfully';
                        var message = document.createElement('p');
                        message.id = 'saved-message';
                        message.textContent = 'Saved successfully';
                        document.getElementById('observable-root').appendChild(message);
                        history.pushState({}, '', '/observable?saved=1');
                      });
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/console":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Console</title></head>
                  <body>
                    <main id="console-root">
                      <h1>Console Workflow</h1>
                      <output id="console-status" role="status">ready</output>
                      <button id="console-action" type="button">Emit console error</button>
                    </main>
                    <script>
                      console.log('fixture console log');
                      console.warn('fixture console warning');
                      console.error('fixture console error');
                      document.getElementById('console-action').addEventListener('click', function () {
                        console.error('fixture action failed');
                        document.getElementById('console-status').textContent = 'action failed';
                      });
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/new-tab":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture New Tab</title></head>
                  <body>
                    <main id="new-tab-page">
                      <h1>New Tab Target</h1>
                    </main>
                  </body>
                </html>
                """
            )
            return

        if path == "/selectors":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head>
                    <title>Fixture Selectors</title>
                    <style>h1 { color: red; }</style>
                  </head>
                  <body>
                    <main id="selector-root">
                      <h1 id="selector-title">Title</h1>
                      <input id="cust" name="custname" value="Ada" />
                    </main>
                  </body>
                </html>
                """
            )
            return

        if path == "/catalog":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Catalog</title></head>
                  <body>
                    <main id="catalog">
                      <h1 id="catalog-title">Automation Catalog</h1>
                      <p class="intro">Pick a deterministic browser automation task.</p>
                      <nav>
                        <a id="docs-link" href="/docs">Docs</a>
                        <a data-testid="pricing-link" href="/pricing">Pricing</a>
                      </nav>
                      <section id="cards" aria-label="Products">
                        <article id="alpha" class="product-card" data-testid="product-alpha">
                          <h2>Alpha Browser</h2>
                          <p class="role">Navigation helper</p>
                          <a class="details" href="/products/alpha">Details</a>
                          <button class="buy" type="button">Choose Alpha</button>
                        </article>
                        <article id="beta" class="product-card" data-testid="product-beta">
                          <h2>Beta Extractor</h2>
                          <p class="role">Structured extraction</p>
                          <a class="details" href="/products/beta">Details</a>
                          <button class="buy" type="button">Choose Beta</button>
                        </article>
                        <article id="gamma" class="product-card" data-testid="product-gamma">
                          <h2>Gamma Waiter</h2>
                          <p class="role">Dynamic waits</p>
                          <a class="details" href="/products/gamma">Details</a>
                          <button class="buy" type="button">Choose Gamma</button>
                        </article>
                      </section>
                      <table id="people">
                        <thead><tr><th>Name</th><th>Role</th></tr></thead>
                        <tbody>
                          <tr><td>Ada</td><td>Engineer</td></tr>
                          <tr><td>Grace</td><td>Researcher</td></tr>
                          <tr><td>Katherine</td><td>Mathematician</td></tr>
                        </tbody>
                      </table>
                      <form id="filter-form" action="/catalog" method="get">
                        <label for="query">Filter</label>
                        <input id="query" name="q" placeholder="search products" />
                        <button id="filter-button" type="submit">Apply</button>
                      </form>
                    </main>
                  </body>
                </html>
                """
            )
            return


        if path == "/link-heavy":
            links = "\n".join(
                f'<a class="story" href="/story/{index}">Story {index}</a>'
                for index in range(75)
            )
            self._send_html(
                f"""
                <!doctype html>
                <html>
                  <head><title>Fixture Link Heavy</title></head>
                  <body>
                    <main id="link-heavy">
                      <h1 id="link-heavy-title">Link Heavy Page</h1>
                      <nav aria-label="Stories">
                        {links}
                      </nav>
                      <form id="search-form" action="/link-heavy" method="get">
                        <label for="search-input">Search stories</label>
                        <input id="search-input" name="q" placeholder="search stories" />
                        <button id="search-button" type="submit">Search</button>
                      </form>
                    </main>
                  </body>
                </html>
                """
            )
            return

        if path == "/links":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Links</title></head>
                  <body>
                    <main id="links-workflow">
                      <h1>Links Workflow</h1>
                      <a id="docs-link" href="/docs">Docs</a>
                      <a id="relative-link" href="../relative/page">Relative Page</a>
                      <a id="blank-link" href="/new-tab" target="_blank">Blank</a>
                      <a id="external-link" href="https://external.example/path" rel="nofollow">External</a>
                    </main>
                  </body>
                </html>
                """
            )
            return

        if path == "/workflow-form":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Workflow Form</title></head>
                  <body>
                    <main id="workflow-form-root">
                      <h1>Workflow Form</h1>
                      <form id="workflow-form" method="post" action="/api/echo.json">
                        <label for="wf-name">Name</label>
                        <input id="wf-name" name="name" value="" />
                        <label for="wf-secret">Secret</label>
                        <input id="wf-secret" name="secret" type="password" value="" />
                        <label for="wf-mode">Mode</label>
                        <select id="wf-mode" name="mode">
                          <option value="basic">Basic</option>
                          <option value="advanced">Advanced</option>
                        </select>
                        <label for="wf-agree">Agree</label>
                        <input id="wf-agree" name="agree" type="checkbox" />
                        <button id="wf-submit" type="submit">Submit</button>
                      </form>
                      <output id="workflow-status">ready</output>
                    </main>
                  </body>
                </html>
                """
            )
            return

        if path == "/network":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Network</title></head>
                  <body>
                    <main id="network-workflow">
                      <h1>Network Workflow</h1>
                      <button id="network-action" type="button">Run network</button>
                      <output id="network-status">idle</output>
                    </main>
                    <script>
                      document.getElementById('network-action').addEventListener('click', async function () {
                        const data = await fetch('/api/data.json?source=fetch', {
                          headers: {'X-Api-Key': 'fixture-secret'}
                        }).then((response) => response.json());
                        const xhrResult = await new Promise((resolve) => {
                          const xhr = new XMLHttpRequest();
                          xhr.open('POST', '/api/echo.json?source=xhr');
                          xhr.setRequestHeader('Content-Type', 'application/json');
                          xhr.onload = () => resolve(xhr.responseText);
                          xhr.send(JSON.stringify({ok: true, item: data.items[0]}));
                        });
                        document.getElementById('network-status').textContent =
                          data.ok && xhrResult ? 'network complete' : 'network failed';
                      });
                    </script>
                  </body>
                </html>
                """
            )
            return

        if path == "/api/data.json":
            self._send_json({"ok": True, "items": ["alpha", "beta"]})
            return

        if path == "/api/echo.json":
            self._send_json({"ok": True, "method": "GET", "query": parse_qs(parsed.query)})
            return

        if path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path == "/status/404":
            self._send_text("fixture missing", status=404)
            return

        if path == "/status/500":
            self._send_text("fixture error", status=500)
            return

        if path == "/iframe":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Iframe</title></head>
                  <body>
                    <section id="frame-content" data-frame="fixture">
                      <h2>Iframe Content</h2>
                      <p id="frame-text">frame ready</p>
                    </section>
                  </body>
                </html>
                """
            )
            return

        if path == "/json":
            payload = json.dumps({"ok": True, "source": "fixture"}).encode("utf-8")
            self._send_bytes(payload, content_type="application/json; charset=utf-8")
            return

        self._send_text("not found", status=404)

    def log_message(
        self, format: str, *args: object
    ) -> None:  # noqa: A002 - stdlib arg name
        """Silence per-request fixture logs for deterministic test output."""

    def _send_html(self, html: str, status: int = 200) -> None:
        body = _dedent_html(html).encode("utf-8")
        self._send_bytes(body, status=status, content_type="text/html; charset=utf-8")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(body, status=status, content_type="application/json; charset=utf-8")

    def _send_text(self, text: str, status: int = 200) -> None:
        self._send_bytes(
            text.encode("utf-8"),
            status=status,
            content_type="text/plain; charset=utf-8",
        )

    def _send_bytes(
        self, body: bytes, status: int = 200, content_type: str = "text/plain"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def local_http_fixture() -> Iterator[str]:
    """Run the deterministic fixture server and yield its base URL."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{0}".format(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _dedent_html(html: str) -> str:
    lines = [line.rstrip() for line in html.strip().splitlines()]
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    prefix = min(indents) if indents else 0
    return "\n".join(line[prefix:] for line in lines) + "\n"


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
