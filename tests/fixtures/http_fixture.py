"""Local deterministic HTTP fixture app for browser and protocol tests."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any, Iterator, cast
from urllib.parse import parse_qs, urlparse


TASK_COMPLETION_DOWNLOAD = b"employee_id,name,department\n0701,Ada Lovelace,Research\n"
TASK_COMPLETION_DOWNLOAD_SHA256 = sha256(TASK_COMPLETION_DOWNLOAD).hexdigest()


@dataclass(frozen=True)
class TaskCompletionScenario:
    """Describe one deterministic 0.7 task-completion fixture route."""

    workload_id: str
    route: str
    title: str
    terminal_selector: str
    counter_key: str | None = None


TASK_COMPLETION_SCENARIOS = (
    TaskCompletionScenario(
        "W01",
        "/form-rich",
        "Rich Form",
        "#submission-status",
        "form_rich_accepted_requests",
    ),
    TaskCompletionScenario(
        "W02",
        "/form-controlled",
        "Controlled Form",
        "#controlled-rendered",
        "form_controlled_accepted_requests",
    ),
    TaskCompletionScenario(
        "W03",
        "/form-validation",
        "Validation Form",
        "#validation-status",
        "validation_accepted_requests",
    ),
    TaskCompletionScenario(
        "W04",
        "/form-upload-submit",
        "Upload Submit",
        "#upload-status",
        "upload_accepted_requests",
    ),
    TaskCompletionScenario("W05", "/dialog", "Dialog", "#dialog-status"),
    TaskCompletionScenario("W06", "/popup", "Popup", "#popup-status"),
    TaskCompletionScenario(
        "W07", "/download", "Download", "#download-status", "download_requests"
    ),
    TaskCompletionScenario(
        "W07",
        "/download-fail",
        "Download Failure",
        "#download-fail-status",
        "download_fail_requests",
    ),
    TaskCompletionScenario("W08", "/click-variants", "Click Variants", "#click-status"),
)


class FixtureState:
    """Thread-safe side-effect evidence for task-completion scenarios."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = {}
        self._events: list[dict[str, Any]] = []

    def record(self, counter: str, **evidence: Any) -> int:
        with self._lock:
            count = self._counters.get(counter, 0) + 1
            self._counters[counter] = count
            self._events.append(
                {
                    "sequence": len(self._events) + 1,
                    "counter": counter,
                    "count": count,
                    "evidence": evidence,
                }
            )
            self._events = self._events[-100:]
            return count

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._events.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": "0.7.5",
                "counters": dict(sorted(self._counters.items())),
                "events": [dict(event) for event in self._events],
                "download": {
                    "filename": "fixture-report.csv",
                    "size_bytes": len(TASK_COMPLETION_DOWNLOAD),
                    "sha256": TASK_COMPLETION_DOWNLOAD_SHA256,
                },
            }


class FixtureHTTPServer(ThreadingHTTPServer):
    fixture_state: FixtureState


class FixtureRequestHandler(BaseHTTPRequestHandler):
    """Serve deterministic pages without external network access."""

    server_version = "DrissionMCPTestFixture/1.0"

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        if parsed.path == "/__fixture__/reset":
            self._state.reset()
            self._send_json(self._state.snapshot())
            return

        fields, filenames = self._read_form_data()
        if parsed.path == "/task/form-rich":
            attempt = self._state.record(
                "form_rich_attempted_requests", fields=fields, filenames=filenames
            )
            if (
                not fields.get("full_name", [""])[0]
                or not fields.get("department", [""])[0]
            ):
                self._send_html(
                    _form_rich_html("Full name and department are required"),
                    status=422,
                )
                return
            accepted = self._state.record("form_rich_accepted_requests", fields=fields)
            self._send_html(
                _task_result_html(
                    "Fixture Rich Form Complete",
                    "submission-status",
                    f"PROFILE-{accepted:04d}",
                    attempt,
                )
            )
            return
        if parsed.path == "/task/form-controlled":
            attempt = self._state.record(
                "form_controlled_attempted_requests", fields=fields
            )
            input_events = int(fields.get("input_events", ["0"])[0] or "0")
            if not fields.get("display_name", [""])[0] or input_events < 1:
                self._send_html(
                    _form_controlled_html("A real input event is required"),
                    status=422,
                )
                return
            accepted = self._state.record(
                "form_controlled_accepted_requests", fields=fields
            )
            self._send_html(
                _task_result_html(
                    "Fixture Controlled Form Complete",
                    "controlled-rendered",
                    f"CONTROLLED-{accepted:04d}",
                    attempt,
                )
            )
            return
        if parsed.path == "/task/form-validation":
            attempt = self._state.record("validation_attempted_requests", fields=fields)
            if fields.get("employee_code", [""])[0] != "DP-070":
                self._send_html(
                    _form_validation_html("Employee code must be DP-070"),
                    status=422,
                )
                return
            accepted = self._state.record("validation_accepted_requests", fields=fields)
            self._send_html(
                _task_result_html(
                    "Fixture Validation Form Complete",
                    "validation-status",
                    f"VALIDATED-{accepted:04d}",
                    attempt,
                )
            )
            return
        if parsed.path == "/task/form-secret-validation":
            attempt = self._state.record(
                "secret_validation_attempted_requests", fields=fields
            )
            password = fields.get("password", [""])[0]
            self._send_html(
                _form_secret_validation_html(
                    f"Password {password} is rejected", attempt=attempt
                ),
                status=422,
            )
            return
        if parsed.path == "/task/form-upload-submit":
            attempt = self._state.record(
                "upload_attempted_requests", fields=fields, filenames=filenames
            )
            if filenames.get("attachment") != "fixture-note.txt":
                self._send_html(
                    _form_upload_submit_html("fixture-note.txt is required"),
                    status=422,
                )
                return
            accepted = self._state.record(
                "upload_accepted_requests", filename="fixture-note.txt"
            )
            self._send_html(
                _task_result_html(
                    "Fixture Upload Submit Complete",
                    "upload-status",
                    f"UPLOAD-{accepted:04d}",
                    attempt,
                    detail="fixture-note.txt",
                )
            )
            return
        if parsed.path == "/api/echo.json":
            payload = {
                "ok": True,
                "method": "POST",
                "query": parse_qs(parsed.query),
                "body": fields.get("_raw", [""])[0],
            }
            self._send_json(payload)
            return
        self._send_text("not found", status=404)

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/__fixture__/state":
            self._send_json(self._state.snapshot())
            return

        if path == "/assets/cacheable.js":
            count = self._state.record("cacheable_resource_requests", path=path)
            self._send_bytes(
                f"window.__cacheVersion = {count};".encode(),
                content_type="application/javascript; charset=utf-8",
                headers={"Cache-Control": "public, max-age=3600"},
            )
            return

        if path == "/assets/blocked-resource.js":
            self._state.record("blocked_resource_requests", path=path)
            self._send_bytes(
                b"window.__blockedResourceLoaded = true;",
                content_type="application/javascript; charset=utf-8",
                headers={"Cache-Control": "no-store"},
            )
            return

        task_page = _task_completion_page(path)
        if task_page is not None:
            self._send_html(task_page)
            return

        if path == "/task/popup-result":
            self._send_html(_popup_result_html())
            return

        if path == "/task/download.csv":
            count = self._state.record("download_requests", path=path)
            self._send_bytes(
                TASK_COMPLETION_DOWNLOAD,
                content_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": 'attachment; filename="fixture-report.csv"',
                    "X-Fixture-Download-Count": str(count),
                },
            )
            return

        if path == "/task/download-fail":
            count = self._state.record("download_fail_requests", path=path)
            self._send_json(
                {"ok": False, "status": "cancelled", "count": count}, status=410
            )
            return

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
                """.format(submitted=_escape_html(submitted))
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
                      <label for="editable-notes">Notes</label>
                      <div id="editable-notes" contenteditable="true"></div>
                      <button id="mode-switch" type="button" role="switch" aria-checked="false">Off</button>
                      <label for="city-picker">City</label>
                      <input id="city-picker" role="combobox" aria-controls="city-options" readonly />
                      <button id="hover-target" type="button">Hover me</button>
                      <output id="hover-status">waiting</output>
                      <section id="deep-target">Deep target</section>
                    </main>
                    <ul id="city-options" role="listbox" hidden>
                      <li role="option" data-value="London" aria-selected="false">London</li>
                      <li role="option" data-value="Shanghai" aria-selected="false">Shanghai</li>
                    </ul>
                    <script>
                      document.getElementById('hover-target').addEventListener('mouseover', function () {
                        document.getElementById('hover-status').textContent = 'hovered';
                      });
                      const modeSwitch = document.getElementById('mode-switch');
                      modeSwitch.addEventListener('click', function () {
                        const checked = this.getAttribute('aria-checked') !== 'true';
                        this.setAttribute('aria-checked', String(checked));
                        this.textContent = checked ? 'On' : 'Off';
                      });
                      const cityPicker = document.getElementById('city-picker');
                      const cityOptions = document.getElementById('city-options');
                      cityPicker.addEventListener('click', () => { cityOptions.hidden = false; });
                      cityOptions.querySelectorAll('[role="option"]').forEach(option => {
                        option.addEventListener('click', () => {
                          cityOptions.querySelectorAll('[role="option"]').forEach(item => {
                            item.setAttribute('aria-selected', String(item === option));
                          });
                          cityPicker.value = option.dataset.value;
                          cityOptions.hidden = true;
                        });
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

        if path == "/document-boundaries":
            self._send_html(
                _document_boundaries_html(int(self.server.server_address[1]))
            )
            return

        if path == "/slider":
            self._send_html(_slider_host_html())
            return

        if path == "/slider-frame":
            self._send_html(_slider_frame_html())
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

        if path == "/request-context":
            user_agent = self.headers.get("User-Agent", "")
            session_header = self.headers.get("X-MCP-Session", "")
            self._send_html(
                f"""
                <!doctype html>
                <html>
                  <head><title>Fixture Request Context</title></head>
                  <body>
                    <output id="request-user-agent" data-value="{_escape_html(user_agent)}"></output>
                    <output id="request-session-header" data-value="{_escape_html(session_header)}"></output>
                  </body>
                </html>
                """
            )
            return

        if path == "/resource-controls":
            self._send_html(
                """
                <!doctype html>
                <html>
                  <head><title>Fixture Resource Controls</title></head>
                  <body><main id="resource-controls">resource controls</main></body>
                  <script src="/assets/cacheable.js"></script>
                  <script src="/assets/blocked-resource.js"></script>
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
            self._send_json(
                {"ok": True, "method": "GET", "query": parse_qs(parsed.query)}
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

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib arg name
        """Silence per-request fixture logs for deterministic test output."""

    def _send_html(self, html: str, status: int = 200) -> None:
        body = _dedent_html(html).encode("utf-8")
        self._send_bytes(body, status=status, content_type="text/html; charset=utf-8")

    @property
    def _state(self) -> FixtureState:
        return cast(FixtureHTTPServer, self.server).fixture_state

    def _read_form_data(self) -> tuple[dict[str, list[str]], dict[str, str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return _parse_multipart(content_type, body)
        text = body.decode("utf-8", errors="replace")
        fields = parse_qs(text, keep_blank_values=True)
        fields["_raw"] = [text]
        return fields, {}

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(
            body, status=status, content_type="application/json; charset=utf-8"
        )

    def _send_text(self, text: str, status: int = 200) -> None:
        self._send_bytes(
            text.encode("utf-8"),
            status=status,
            content_type="text/plain; charset=utf-8",
        )

    def _send_bytes(
        self,
        body: bytes,
        status: int = 200,
        content_type: str = "text/plain",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def local_http_fixture() -> Iterator[str]:
    """Run the deterministic fixture server and yield its base URL."""

    server = FixtureHTTPServer(("127.0.0.1", 0), FixtureRequestHandler)
    server.fixture_state = FixtureState()
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


def _parse_multipart(
    content_type: str, body: bytes
) -> tuple[dict[str, list[str]], dict[str, str]]:
    from email import policy
    from email.parser import BytesParser

    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\n\r\n" + body
    )
    fields: dict[str, list[str]] = {}
    filenames: dict[str, str] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        if filename:
            filenames[name] = filename
            continue
        value = part.get_content()
        fields.setdefault(name, []).append(
            value if isinstance(value, str) else value.decode("utf-8")
        )
    return fields, filenames


def _task_completion_page(path: str) -> str | None:
    pages = {
        "/form-rich": _form_rich_html,
        "/form-controlled": _form_controlled_html,
        "/form-validation": _form_validation_html,
        "/form-secret-validation": _form_secret_validation_html,
        "/form-upload-submit": _form_upload_submit_html,
        "/dialog": _dialog_html,
        "/popup": _popup_html,
        "/download": _download_html,
        "/download-fail": _download_fail_html,
        "/click-variants": _click_variants_html,
    }
    factory = pages.get(path)
    return factory() if factory else None


def _form_rich_html(status: str = "ready") -> str:
    return f"""
    <!doctype html>
    <html><head><title>Fixture Rich Form</title></head><body>
      <form id="profile-form" action="/task/form-rich" method="post">
        <label for="full-name">Full name</label>
        <input id="full-name" name="full_name" required />
        <label for="alias-id">Alias</label>
        <input id="alias-id" name="alias_name" />
        <input id="contact-name" name="contact_name" />
        <label for="nickname">Nickname</label>
        <input id="nickname" name="nickname" placeholder="Preferred nickname" />
        <input data-testid="explicit-css-field" value="" />
        <label for="access-code">Access code</label>
        <input id="access-code" name="access_code" type="password" value="fixture-password" />
        <label for="employee-id">Employee ID</label>
        <input id="employee-id" name="employee_id" value="EMP-000" readonly />
        <label for="archived-reason">Archived reason</label>
        <input id="archived-reason" name="archived_reason" value="n/a" disabled />
        <label for="department">Business unit</label>
        <select id="department" name="department">
          <option value="Operations">Operations</option>
          <option value="Research">Research</option>
        </select>
        <label><input id="updates" name="updates" type="checkbox" value="yes" /> Receive updates</label>
        <label for="start-date">Start date</label><input id="start-date" name="start_date" type="date" />
        <label for="start-time">Start time</label><input id="start-time" name="start_time" type="time" />
        <label for="skills">Skills</label>
        <select id="skills" name="skills" multiple>
          <option value="writing">Writing</option><option value="analysis">Analysis</option>
        </select>
        <label for="bio">Bio</label><div id="bio" role="textbox" contenteditable="true"></div>
        <label for="office">Office</label><input id="office" name="office" role="combobox" aria-controls="office-options" aria-expanded="false" />
        <ul id="office-options" role="listbox"><li role="option" aria-selected="false" data-value="London">London</li><li role="option" aria-selected="false" data-value="Shanghai">Shanghai</li></ul>
        <input id="bio-value" name="bio" type="hidden" />
        <button id="profile-submit" type="submit">Create profile</button>
      </form>
      <output id="submission-status" role="status">{_escape_html(status)}</output>
      <output id="form-event-state" data-input-events="0" data-change-events="0">input=0; change=0; controls=</output>
      <script>
        const eventState = {{input: 0, change: 0, controls: []}};
        const eventOutput = document.getElementById('form-event-state');
        const renderEventState = () => {{
          eventOutput.dataset.inputEvents = eventState.input;
          eventOutput.dataset.changeEvents = eventState.change;
          eventOutput.textContent = `input=${{eventState.input}}; change=${{eventState.change}}; controls=${{eventState.controls.join(',')}}`;
        }};
        document.querySelectorAll('#profile-form input, #profile-form select, #profile-form [contenteditable="true"]').forEach(control => {{
          control.addEventListener('input', () => {{ eventState.input += 1; if (control.id) eventState.controls.push(`${{control.id}}:input`); renderEventState(); }});
          control.addEventListener('change', () => {{ eventState.change += 1; if (control.id) eventState.controls.push(`${{control.id}}:change`); renderEventState(); }});
        }});
        const bio = document.getElementById('bio');
        bio.addEventListener('input', () => document.getElementById('bio-value').value = bio.textContent);
        document.querySelectorAll('[role=option]').forEach(option => option.addEventListener('click', () => {{
          document.querySelectorAll('[role=option]').forEach(item => item.setAttribute('aria-selected', String(item === option)));
          document.getElementById('office').value = option.dataset.value;
          document.getElementById('office').dispatchEvent(new Event('change', {{bubbles: true}}));
        }}));
      </script>
    </body></html>
    """


def _form_controlled_html(status: str = "empty; input=0; change=0") -> str:
    return f"""
    <!doctype html>
    <html><head><title>Fixture Controlled Form</title></head><body>
      <form id="controlled-form" action="/task/form-controlled" method="post">
        <label for="controlled-name">Display name</label>
        <input id="controlled-name" name="display_name" autocomplete="off" />
        <input id="controlled-evidence" name="input_events" type="hidden" value="0" />
        <button id="controlled-submit" type="submit">Save controlled value</button>
      </form>
      <output id="controlled-rendered">{_escape_html(status)}</output>
      <script>
        const input = document.getElementById('controlled-name');
        const output = document.getElementById('controlled-rendered');
        const evidence = document.getElementById('controlled-evidence');
        const state = {{value: '', input: 0, change: 0}};
        const render = () => output.textContent = `${{state.value || 'empty'}}; input=${{state.input}}; change=${{state.change}}`;
        input.addEventListener('input', event => {{ state.value = event.target.value; state.input += 1; evidence.value = state.input; render(); }});
        input.addEventListener('change', () => {{ state.change += 1; render(); }});
        window.__controlledState = state;
      </script>
    </body></html>
    """


def _form_validation_html(status: str = "") -> str:
    server_validation = (
        f'<p id="employee-code-server-error" role="alert" data-server-validation>{_escape_html(status)}</p>'
        if status
        else ""
    )
    return f"""
    <!doctype html>
    <html><head><title>Fixture Validation Form</title></head><body>
      <form id="validation-form" action="/task/form-validation" method="post">
        <label for="employee-code">Employee code</label>
        <input id="employee-code" name="employee_code" required pattern="DP-[0-9]{{3}}" aria-describedby="employee-code-help" />
        <p id="employee-code-help">Use an employee code in the DP-000 format</p>
        {server_validation}
        <button id="validation-submit" type="submit">Submit employee</button>
      </form>
      <output id="validation-status" role="status">ready</output>
      <script>
        const employeeCode = document.getElementById('employee-code');
        employeeCode.addEventListener('input', () => document.getElementById('employee-code-server-error')?.remove());
      </script>
    </body></html>
    """


def _form_upload_submit_html(status: str = "ready") -> str:
    return f"""
    <!doctype html>
    <html><head><title>Fixture Upload Submit</title></head><body>
      <form id="upload-submit-form" action="/task/form-upload-submit" method="post" enctype="multipart/form-data">
        <label for="case-name">Case name</label><input id="case-name" name="case_name" required />
        <label for="attachment">Attachment</label><input id="attachment" name="attachment" type="file" required />
        <output id="selected-file">none</output>
        <button id="upload-submit" type="submit">Upload and submit</button>
      </form>
      <output id="upload-status" role="status">{_escape_html(status)}</output>
      <script>document.getElementById('attachment').addEventListener('change', event => document.getElementById('selected-file').textContent = event.target.files[0]?.name || 'none');</script>
    </body></html>
    """


def _form_secret_validation_html(status: str = "", *, attempt: int = 0) -> str:
    server_validation = (
        f'<p id="secret-server-error" role="alert" data-server-validation>{_escape_html(status)}</p>'
        if status
        else ""
    )
    return f"""
    <!doctype html>
    <html><head><title>Secret Validation</title></head><body>
      <form id="secret-validation-form" action="/task/form-secret-validation" method="post">
        <label for="secret-password">Password</label>
        <input id="secret-password" name="password" type="password" value="fixture-password" />
        <button id="secret-validation-submit" type="submit">Submit secret</button>
      </form>
      {server_validation}
      <data id="secret-attempt" value="{attempt}">{attempt}</data>
    </body></html>
    """


def _task_result_html(
    title: str,
    status_id: str,
    business_id: str,
    attempt: int,
    *,
    detail: str = "",
) -> str:
    return f"""
    <!doctype html>
    <html><head><title>{_escape_html(title)}</title></head><body>
      <output id="{_escape_html(status_id)}" role="status" class="success">completed</output>
      <data id="business-id" value="{_escape_html(business_id)}">{_escape_html(business_id)}</data>
      <data id="request-attempt" value="{attempt}">{attempt}</data>
      <output id="result-detail">{_escape_html(detail)}</output>
    </body></html>
    """


def _dialog_html() -> str:
    return """
    <!doctype html>
    <html><head><title>Fixture Dialog</title></head><body>
      <button id="alert-button" type="button">Alert</button>
      <button id="confirm-button" type="button">Confirm</button>
      <button id="prompt-button" type="button">Prompt</button>
      <output id="dialog-status">ready</output>
      <script>
        const status = document.getElementById('dialog-status');
        document.getElementById('alert-button').onclick = () => { alert('Fixture alert'); status.textContent = 'alert accepted'; };
        document.getElementById('confirm-button').onclick = () => status.textContent = confirm('Fixture confirm') ? 'confirm accepted' : 'confirm dismissed';
        document.getElementById('prompt-button').onclick = () => { const value = prompt('Fixture prompt', ''); status.textContent = value === null ? 'prompt dismissed' : `prompt accepted:${value}`; };
      </script>
    </body></html>
    """


def _popup_html() -> str:
    return """
    <!doctype html>
    <html><head><title>Fixture Popup</title></head><body>
      <a id="popup-link" href="/task/popup-result" target="_blank">Open work item</a>
      <output id="popup-status">ready</output>
      <script>document.getElementById('popup-link').addEventListener('click', () => document.getElementById('popup-status').textContent = 'popup requested');</script>
    </body></html>
    """


def _popup_result_html() -> str:
    return """
    <!doctype html>
    <html><head><title>Fixture Popup Result</title></head><body>
      <button id="popup-complete" type="button">Complete work item</button>
      <output id="popup-result">ready</output>
      <script>document.getElementById('popup-complete').onclick = () => document.getElementById('popup-result').textContent = 'popup work complete';</script>
    </body></html>
    """


def _download_html() -> str:
    return """
    <!doctype html>
    <html><head><title>Fixture Download</title></head><body>
      <a id="download-link" href="/task/download.csv" download="fixture-report.csv">Download report</a>
      <output id="download-status">ready</output>
    </body></html>
    """


def _download_fail_html() -> str:
    return """
    <!doctype html>
    <html><head><title>Fixture Download Failure</title></head><body>
      <a id="download-fail-link" href="/task/download-fail" download="missing.csv">Download missing report</a>
      <output id="download-fail-status">ready</output>
    </body></html>
    """


def _click_variants_html() -> str:
    return """
    <!doctype html>
    <html><head><title>Fixture Click Variants</title></head><body>
      <button id="click-target" type="button">Action target</button>
      <input id="shortcut-input" value="shortcut source" />
      <output id="click-status">ready</output>
      <script>
        const target = document.getElementById('click-target');
        const status = document.getElementById('click-status');
        const counts = {click: 0, dblclick: 0, contextmenu: 0, shortcut: 0};
        const events = [];
        const render = kind => status.textContent = `${kind}; click=${counts.click}; dblclick=${counts.dblclick}; contextmenu=${counts.contextmenu}; shortcut=${counts.shortcut}`;
        const record = event => events.push({
          type: event.type,
          button: event.button,
          detail: event.detail,
          trusted: event.isTrusted,
        });
        target.addEventListener('click', event => { record(event); counts.click += 1; render('click'); });
        target.addEventListener('dblclick', event => { record(event); counts.dblclick += 1; render('dblclick'); });
        target.addEventListener('contextmenu', event => { event.preventDefault(); record(event); counts.contextmenu += 1; render('contextmenu'); });
        document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); counts.shortcut += 1; render('shortcut'); } });
        window.__clickCounts = counts;
        window.__clickEvents = events;
      </script>
    </body></html>
    """


def _slider_host_html() -> str:
    """Return a deterministic slider page spanning iframe and nested open Shadow DOM."""

    return """
    <!doctype html>
    <html>
      <head>
        <title>Fixture Slider</title>
        <style>
          html, body { margin: 0; padding: 0; }
          body { min-height: 700px; font-family: sans-serif; }
          iframe { position: fixed; left: 40px; top: 40px; width: 440px; height: 180px; border: 0; }
          #shadow-slider-host { position: fixed; left: 40px; top: 280px; width: 440px; height: 180px; }
        </style>
      </head>
      <body>
        <iframe id="slider-frame" src="/slider-frame" title="Slider iframe"></iframe>
        <div id="shadow-slider-host"></div>
        <script>
          const outerHost = document.getElementById('shadow-slider-host');
          const outerRoot = outerHost.attachShadow({mode: 'open'});
          outerRoot.innerHTML = '<div id="nested-slider-host"></div>';
          const nestedHost = outerRoot.querySelector('#nested-slider-host');
          const root = nestedHost.attachShadow({mode: 'open'});
          root.innerHTML = `
            <style>
              :host { display: block; width: 440px; height: 180px; }
              .challenge { width: 400px; padding: 20px; background: #f6f7f9; }
              .track { position: relative; width: 320px; height: 18px; margin-top: 24px; background: #d8dde6; border-radius: 9px; }
              .knob { position: absolute; left: 0; top: -9px; width: 36px; height: 36px; border: 0; border-radius: 50%; background: #2563eb; cursor: grab; }
              .knob:active { cursor: grabbing; }
            </style>
            <section class="challenge" data-slider-context="shadow">
              <strong>Nested Shadow DOM slider verification fixture</strong>
              <div class="track" id="shadow-track"><button class="knob" id="shadow-knob" aria-label="Drag slider"></button></div>
              <output id="shadow-status">pending</output>
            </section>`;
          window.__shadowSlider = installSlider(root, 'shadow');

          function installSlider(root, label) {
            const track = root.querySelector('.track');
            const knob = root.querySelector('.knob');
            const status = root.querySelector('output');
            const state = {label, dragging: false, grabOffset: 0, samples: [], accepted: false};
            const record = event => state.samples.push({
              type: event.type,
              x: event.clientX,
              y: event.clientY,
              buttons: event.buttons,
              time: performance.now(),
              trusted: event.isTrusted,
              path: event.composedPath().map(node => node.id || node.tagName || '').filter(Boolean).slice(0, 10)
            });
            knob.addEventListener('mousedown', event => {
              record(event);
              state.dragging = true;
              state.grabOffset = event.clientX - knob.getBoundingClientRect().left;
            });
            window.addEventListener('mousemove', event => {
              if (!state.dragging) return;
              record(event);
              const rect = track.getBoundingClientRect();
              const max = rect.width - knob.offsetWidth;
              const left = Math.max(0, Math.min(max, event.clientX - rect.left - state.grabOffset));
              knob.style.left = `${left}px`;
            });
            window.addEventListener('mouseup', event => {
              if (!state.dragging) return;
              record(event);
              state.dragging = false;
              state.metrics = classify(state.samples, track, knob);
              state.accepted = state.metrics.accepted;
              status.textContent = state.accepted ? 'passed' : 'rejected';
            });
            return state;
          }

          function classify(samples, track, knob) {
            const down = samples.filter(item => item.type === 'mousedown');
            const allMoves = samples.filter(item => item.type === 'mousemove');
            const moves = allMoves.filter(item => item.buttons === 1);
            const up = samples.filter(item => item.type === 'mouseup');
            const deltas = moves.slice(1).map((item, index) => ({
              dx: Math.abs(item.x - moves[index].x),
              dt: item.time - moves[index].time
            }));
            const third = Math.max(2, Math.floor(deltas.length / 3));
            const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
            const spatial = deltas.map(item => item.dx);
            const intervals = deltas.map(item => item.dt);
            const firstMean = mean(spatial.slice(0, Math.min(3, spatial.length)));
            const middleMean = mean(spatial.slice(third, third * 2));
            const lastMean = mean(spatial.slice(-Math.min(3, spatial.length)));
            const rollingMeans = spatial.slice(0, -2).map((_, index) => mean(spatial.slice(index, index + 3)));
            const peakMean = rollingMeans.length ? Math.max(...rollingMeans) : 0;
            const trackRect = track.getBoundingClientRect();
            const knobRect = knob.getBoundingClientRect();
            const maxTravel = trackRect.width - knobRect.width;
            const finalProgress = maxTravel ? (knobRect.left - trackRect.left) / maxTravel : 0;
            const yValues = moves.map(item => item.y);
            const durationMs = down.length && up.length ? up[0].time - down[0].time : 0;
            // Keep the observed spread for diagnostics; browser scheduling is not
            // a stable semantic contract for the deterministic pointer profile.
            const intervalSpreadMs = intervals.length ? Math.max(...intervals) - Math.min(...intervals) : 0;
            const maxStepPx = spatial.length ? Math.max(...spatial) : Infinity;
            const eased = peakMean > firstMean * 1.20 && peakMean > lastMean * 1.20;
            const accepted = down.length === 1 && up.length === 1 && moves.length >= 20 &&
              samples.every(item => item.trusted) && moves.every(item => item.buttons === 1) &&
              finalProgress >= 0.985 && durationMs >= 180 && durationMs <= 2500 &&
              maxStepPx <= 40 && eased;
            return {
              accepted, downCount: down.length, moveCount: moves.length, unheldMoveCount: allMoves.length - moves.length, upCount: up.length,
              allTrusted: samples.every(item => item.trusted), heldMoves: moves.every(item => item.buttons === 1),
              finalProgress, durationMs, intervalSpreadMs, maxStepPx, firstMean, middleMean, lastMean, peakMean,
              eased, yRange: yValues.length ? Math.max(...yValues) - Math.min(...yValues) : 0
            };
          }
        </script>
      </body>
    </html>
    """


def _document_boundaries_html(port: int) -> str:
    """Return cross-origin iframe and closed Shadow DOM capability fixtures."""

    return f"""
    <!doctype html>
    <html>
      <head><title>Fixture Document Boundaries</title></head>
      <body>
        <main id="document-boundaries">
          <h1>Document Boundaries</h1>
          <iframe
            id="oopif-frame"
            src="http://localhost:{port}/iframe"
            title="Cross-origin OOPIF"
          ></iframe>
          <div id="closed-shadow-host"></div>
        </main>
        <script>
          const host = document.getElementById('closed-shadow-host');
          const root = host.attachShadow({{mode: 'closed'}});
          root.innerHTML = `
            <section id="closed-shadow-content">
              <button id="closed-shadow-button" type="button">Closed Action</button>
              <ul>
                <li class="closed-shadow-item">Closed Alpha</li>
                <li class="closed-shadow-item">Closed Beta</li>
              </ul>
            </section>
          `;
        </script>
      </body>
    </html>
    """


def _slider_frame_html() -> str:
    """Return the same-origin iframe half of the deterministic slider fixture."""

    return """
    <!doctype html>
    <html>
      <head>
        <title>Fixture Slider Frame</title>
        <style>
          html, body { margin: 0; padding: 0; font-family: sans-serif; }
          .challenge { width: 400px; padding: 20px; background: #f6f7f9; }
          .track { position: relative; width: 320px; height: 18px; margin-top: 24px; background: #d8dde6; border-radius: 9px; }
          .knob { position: absolute; left: 0; top: -9px; width: 36px; height: 36px; border: 0; border-radius: 50%; background: #16a34a; cursor: grab; }
          .knob:active { cursor: grabbing; }
        </style>
      </head>
      <body>
        <section class="challenge" data-slider-context="iframe">
          <strong>Same-origin iframe slider verification fixture</strong>
          <div class="track" id="frame-track"><button class="knob" id="frame-knob" aria-label="Drag slider"></button></div>
          <output id="frame-status">pending</output>
        </section>
        <script>
          const track = document.getElementById('frame-track');
          const knob = document.getElementById('frame-knob');
          const status = document.getElementById('frame-status');
          const state = window.__frameSlider = {dragging: false, grabOffset: 0, samples: [], accepted: false};
          const record = event => state.samples.push({
            type: event.type, x: event.clientX, y: event.clientY, buttons: event.buttons,
            time: performance.now(), trusted: event.isTrusted,
            path: event.composedPath().map(node => node.id || node.tagName || '').filter(Boolean).slice(0, 10)
          });
          knob.addEventListener('mousedown', event => {
            record(event);
            state.dragging = true;
            state.grabOffset = event.clientX - knob.getBoundingClientRect().left;
          });
          window.addEventListener('mousemove', event => {
            if (!state.dragging) return;
            record(event);
            const rect = track.getBoundingClientRect();
            const max = rect.width - knob.offsetWidth;
            const left = Math.max(0, Math.min(max, event.clientX - rect.left - state.grabOffset));
            knob.style.left = `${left}px`;
          });
          window.addEventListener('mouseup', event => {
            if (!state.dragging) return;
            record(event);
            state.dragging = false;
            state.metrics = classify(state.samples);
            state.accepted = state.metrics.accepted;
            status.textContent = state.accepted ? 'passed' : 'rejected';
          });
          function classify(samples) {
            const down = samples.filter(item => item.type === 'mousedown');
            const allMoves = samples.filter(item => item.type === 'mousemove');
            const moves = allMoves.filter(item => item.buttons === 1);
            const up = samples.filter(item => item.type === 'mouseup');
            const deltas = moves.slice(1).map((item, index) => ({dx: Math.abs(item.x - moves[index].x), dt: item.time - moves[index].time}));
            const third = Math.max(2, Math.floor(deltas.length / 3));
            const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
            const spatial = deltas.map(item => item.dx);
            const intervals = deltas.map(item => item.dt);
            const firstMean = mean(spatial.slice(0, Math.min(3, spatial.length)));
            const middleMean = mean(spatial.slice(third, third * 2));
            const lastMean = mean(spatial.slice(-Math.min(3, spatial.length)));
            const rollingMeans = spatial.slice(0, -2).map((_, index) => mean(spatial.slice(index, index + 3)));
            const peakMean = rollingMeans.length ? Math.max(...rollingMeans) : 0;
            const trackRect = track.getBoundingClientRect();
            const knobRect = knob.getBoundingClientRect();
            const maxTravel = trackRect.width - knobRect.width;
            const finalProgress = maxTravel ? (knobRect.left - trackRect.left) / maxTravel : 0;
            const yValues = moves.map(item => item.y);
            const durationMs = down.length && up.length ? up[0].time - down[0].time : 0;
            // Keep the observed spread for diagnostics; browser scheduling is not
            // a stable semantic contract for the deterministic pointer profile.
            const intervalSpreadMs = intervals.length ? Math.max(...intervals) - Math.min(...intervals) : 0;
            const maxStepPx = spatial.length ? Math.max(...spatial) : Infinity;
            const eased = peakMean > firstMean * 1.20 && peakMean > lastMean * 1.20;
            const accepted = down.length === 1 && up.length === 1 && moves.length >= 20 &&
              samples.every(item => item.trusted) && moves.every(item => item.buttons === 1) &&
              finalProgress >= 0.985 && durationMs >= 180 && durationMs <= 2500 &&
              maxStepPx <= 40 && eased;
            return {
              accepted, downCount: down.length, moveCount: moves.length, unheldMoveCount: allMoves.length - moves.length, upCount: up.length,
              allTrusted: samples.every(item => item.trusted), heldMoves: moves.every(item => item.buttons === 1),
              finalProgress, durationMs, intervalSpreadMs, maxStepPx, firstMean, middleMean, lastMean, peakMean,
              eased, yRange: yValues.length ? Math.max(...yValues) - Math.min(...yValues) : 0
            };
          }
        </script>
      </body>
    </html>
    """


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
