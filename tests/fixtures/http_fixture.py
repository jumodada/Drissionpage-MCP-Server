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
