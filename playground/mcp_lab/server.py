"""Deterministic local business site for DrissionPage MCP playground checks."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Iterator
from urllib.parse import parse_qs, quote, urlparse


@dataclass(frozen=True)
class LabServer:
    """Running local MCP lab site."""

    base_url: str
    server: ThreadingHTTPServer
    thread: Thread


MANIFEST: dict[str, object] = {
    "name": "DrissionPage MCP Lab",
    "version": "1.0",
    "scenarios": ["forms", "commerce", "social-notes", "timeline", "recovery"],
    "routes": {
        "home": "/",
        "forms": "/cases/forms",
        "commerce": "/scenarios/commerce",
        "social-notes": "/scenarios/social-notes",
        "timeline": "/scenarios/timeline",
        "manifest": "/api/manifest.json",
    },
}


@contextmanager
def local_lab_server(host: str = "127.0.0.1", port: int = 0) -> Iterator[str]:
    """Run the deterministic local MCP lab site and yield its base URL."""

    server = ThreadingHTTPServer((host, port), LabRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


class LabRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler with deterministic pages and JSON endpoints."""

    server_version = "DrissionMcpLab/1.0"

    def do_GET(self) -> None:  # noqa: N802 - stdlib API name.
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        routes = {
            "/": lambda: _home_page(),
            "/cases/forms": lambda: _forms_page(),
            "/scenarios/commerce": lambda: _commerce_page(),
            "/scenarios/commerce/search": lambda: _commerce_search_page(
                query.get("q", ["耳机"])[0]
            ),
            "/scenarios/commerce/item/aurora-headphones": _commerce_item_page,
            "/scenarios/commerce/cart": _commerce_cart_page,
            "/scenarios/commerce/checkout": _commerce_checkout_page,
            "/scenarios/commerce/order-result": _commerce_order_result_page,
            "/scenarios/social-notes": _social_notes_page,
            "/scenarios/social-notes/note/note-002": _social_note_detail_page,
            "/scenarios/social-notes/security-check": _social_notes_security_page,
            "/scenarios/timeline": _timeline_page,
            "/api/manifest.json": lambda: json.dumps(MANIFEST, ensure_ascii=False),
            "/api/commerce/products.json": _commerce_products_json,
            "/api/social-notes/feed.json": _social_notes_feed_json,
            "/api/timeline/posts.json": _timeline_posts_json,
            "/api/recovery/protected.json": _protected_json,
        }

        handler = routes.get(path)
        if handler is None:
            self._send_text(_not_found_page(path), status=HTTPStatus.NOT_FOUND)
            return

        body = handler()
        if path.startswith("/api/"):
            self._send_text(body, content_type="application/json; charset=utf-8")
        else:
            self._send_text(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib API name.
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        payload = {
            "ok": True,
            "path": parsed.path,
            "body": raw,
            "content_type": self.headers.get("Content-Type", ""),
        }
        self._send_text(
            json.dumps(payload, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    def log_message(self, *_args: object) -> None:
        """Silence request logs during test runs."""

    def _send_text(
        self,
        body: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _page(title: str, body: str, *, mobile: bool = False) -> str:
    viewport = "width=device-width,initial-scale=1" if mobile else "width=device-width"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="{viewport}" />
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, Arial, sans-serif; }}
    body {{ margin: 0; background: #f7f7fb; color: #202336; }}
    header, main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    header {{ background: #fff; border-bottom: 1px solid #e7e8f2; }}
    nav a, .link {{ margin-right: 16px; color: #2454d6; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
    .card, form, .panel {{ background: #fff; border: 1px solid #e1e4ef; border-radius: 14px; padding: 16px; }}
    .price {{ color: #c04700; font-weight: 700; }}
    label {{ display: block; margin: 10px 0 4px; font-weight: 600; }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; padding: 9px; border: 1px solid #bbc1d5; border-radius: 8px; }}
    button, .button {{ display: inline-block; margin-top: 12px; padding: 9px 14px; border: 0; border-radius: 9px; background: #2454d6; color: #fff; text-decoration: none; }}
    .mobile-shell {{ max-width: 430px; margin: 0 auto; background: #fff; min-height: 100vh; }}
    .note-grid {{ columns: 2; column-gap: 12px; }}
    .note-card {{ break-inside: avoid; margin: 0 0 12px; }}
    .post {{ border-left: 3px solid #2454d6; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <nav aria-label="MCP Lab scenarios">
      <a href="/cases/forms" data-testid="nav-forms">Forms</a>
      <a href="/scenarios/commerce" data-testid="nav-commerce">Commerce</a>
      <a href="/scenarios/social-notes" data-testid="nav-social-notes">Social Notes</a>
      <a href="/scenarios/timeline" data-testid="nav-timeline">Timeline</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>"""


def _home_page() -> str:
    return _page(
        "DrissionPage MCP Lab",
        """
<section class="panel" data-testid="lab-index">
  <h2>Deterministic MCP business fixtures</h2>
  <p>Use this site to test page understanding, form inspection, recovery hints,
  and realistic browser automation flows without third-party network access.</p>
  <ul>
    <li><a href="/cases/forms">Form inspection fixture</a></li>
    <li><a href="/scenarios/commerce">Taobao-like commerce scenario</a></li>
    <li><a href="/scenarios/social-notes">Xiaohongshu-like mobile scenario</a></li>
    <li><a href="/scenarios/timeline">Twitter-like timeline scenario</a></li>
  </ul>
</section>
""",
    )


def _forms_page() -> str:
    return _page(
        "MCP Lab Form Case",
        """
<form id="fixture-form" data-testid="fixture-form" method="post" action="/api/forms/submit">
  <h2>Profile form</h2>
  <label for="full-name">Full name</label>
  <input id="full-name" name="fullName" value="Ada Lovelace" required />

  <label for="secret">Password</label>
  <input id="secret" name="password" type="password" value="fixture-secret" />

  <label for="plan">Plan</label>
  <select id="plan" name="plan" required>
    <option value="starter">Starter</option>
    <option value="pro" selected>Pro</option>
    <option value="enterprise">Enterprise</option>
  </select>

  <label for="bio">Bio</label>
  <textarea id="bio" name="bio" readonly>First programmer profile</textarea>

  <label><input id="newsletter" name="newsletter" type="checkbox" checked /> Subscribe</label>
  <button id="save-profile" type="submit">Save profile</button>
</form>
""",
    )


def _commerce_page() -> str:
    return _page(
        "MockMall Commerce",
        f"""
<form id="commerce-search-form" data-testid="commerce-search-form" action="/scenarios/commerce/search" method="get">
  <label for="commerce-query">Search products</label>
  <input id="commerce-query" name="q" value="耳机" placeholder="Search MockMall" />
  <label for="sort">Sort</label>
  <select id="sort" name="sort">
    <option value="popular" selected>Popular</option>
    <option value="price-asc">Price ascending</option>
  </select>
  <button id="commerce-search-button" data-testid="commerce-search-button" type="submit">Search</button>
</form>
<section class="grid" data-testid="commerce-product-grid">
  {_product_card('aurora-headphones', 'Aurora Headphones', '¥399', 'Noise cancelling wireless headphones')}
  {_product_card('travel-keyboard', 'Travel Keyboard', '¥259', 'Low-profile mechanical keyboard')}
  {_product_card('creator-light', 'Creator Light', '¥189', 'Portable fill light for live commerce')}
</section>
<a class="button" data-testid="commerce-cart-link" href="/scenarios/commerce/cart">Open cart</a>
""",
    )


def _commerce_search_page(query: str) -> str:
    safe_query = quote(query)
    return _page(
        "MockMall Search Results",
        f"""
<p data-testid="search-summary">Search results for {query}</p>
<a href="/scenarios/commerce?prefill={safe_query}">Back to commerce home</a>
<section class="grid" data-testid="commerce-search-results">
  {_product_card('aurora-headphones', 'Aurora Headphones', '¥399', f'Matched query {query}')}
  {_product_card('studio-earbuds', 'Studio Earbuds', '¥299', f'Compact result for {query}')}
</section>
""",
    )


def _commerce_item_page() -> str:
    return _page(
        "Aurora Headphones Detail",
        """
<article id="item-detail" data-testid="commerce-item-detail" class="panel">
  <h2>Aurora Headphones</h2>
  <p class="price">¥399</p>
  <p>Deterministic product detail with SKU choices and shipping promise.</p>
  <form id="sku-form" data-testid="sku-form" action="/api/commerce/cart.json" method="post">
    <label for="sku-color">Color</label>
    <select id="sku-color" name="color"><option selected>Moon White</option><option>Night Black</option></select>
    <label for="sku-quantity">Quantity</label>
    <input id="sku-quantity" name="quantity" type="number" value="1" min="1" />
    <button id="add-to-cart" data-testid="add-to-cart" type="submit">Add to cart</button>
  </form>
</article>
""",
    )


def _commerce_cart_page() -> str:
    return _page(
        "MockMall Cart",
        """
<section class="panel" data-testid="cart-summary">
  <h2>Shopping cart</h2>
  <label><input id="cart-select-aurora" type="checkbox" checked /> Aurora Headphones × 1</label>
  <p class="price" data-testid="cart-total">Total: ¥399</p>
  <a class="button" data-testid="checkout-link" href="/scenarios/commerce/checkout">Checkout</a>
</section>
""",
    )


def _commerce_checkout_page() -> str:
    return _page(
        "MockMall Checkout",
        """
<form id="checkout-form" data-testid="checkout-form" action="/scenarios/commerce/order-result" method="get">
  <h2>Confirm order</h2>
  <label for="address">Address</label>
  <input id="address" name="address" value="No. 42 Deterministic Road" required />
  <label for="payment">Payment</label>
  <select id="payment" name="payment"><option selected>MockPay</option><option>Invoice later</option></select>
  <label for="memo">Memo</label>
  <textarea id="memo" name="memo">Deliver before Friday</textarea>
  <button id="submit-order" data-testid="submit-order" type="submit">Submit order</button>
</form>
""",
    )


def _commerce_order_result_page() -> str:
    return _page(
        "Order Submitted",
        """
<section class="panel" data-testid="order-result">
  <h2>Order submitted</h2>
  <p id="order-id">TBMOCK-000001</p>
  <ol><li>Paid</li><li>Packing</li><li>Shipping scheduled</li></ol>
</section>
""",
    )


def _product_card(slug: str, name: str, price: str, description: str) -> str:
    return f"""
<article id="product-{slug}" class="card product-card" data-testid="product-card-{slug}">
  <h3>{name}</h3>
  <p>{description}</p>
  <p class="price">{price}</p>
  <a data-testid="product-link-{slug}" href="/scenarios/commerce/item/{slug}">View details</a>
  <button data-testid="quick-add-{slug}">Quick add</button>
</article>
"""


def _social_notes_page() -> str:
    return _page(
        "Mock Red Notes",
        f"""
<div class="mobile-shell" data-testid="social-notes-shell">
  <section class="panel" data-testid="open-app-banner">Open app for smoother browsing</section>
  <form id="notes-search-form" data-testid="notes-search-form" action="/scenarios/social-notes" method="get">
    <label for="notes-query">Search notes</label>
    <input id="notes-query" name="q" value="咖啡" />
    <button id="notes-search-button" type="submit">Search</button>
  </form>
  <nav aria-label="Channels" data-testid="notes-channel-tabs">
    <button data-channel="food">Food</button><button data-channel="travel">Travel</button><button data-channel="tech">Tech</button>
  </nav>
  <section class="note-grid" data-testid="notes-feed">
    {_note_card('note-001', 'City coffee map', '12 cafes saved', 'coffee')}
    {_note_card('note-002', 'Weekend market guide', '评论 36 · 收藏 88', 'market')}
    {_note_card('note-003', 'Desk setup checklist', 'likes 128', 'setup')}
  </section>
</div>
""",
        mobile=True,
    )


def _social_note_detail_page() -> str:
    return _page(
        "Weekend Market Guide",
        """
<article class="mobile-shell panel" data-testid="note-detail-note-002">
  <h2>Weekend market guide</h2>
  <p>Three deterministic stalls, two routes, one coffee stop.</p>
  <button data-testid="note-like">Like</button>
  <button data-testid="note-save">Save</button>
  <section data-testid="note-comments">
    <h3>Comments</h3>
    <p data-testid="comment-1">Grace: Try the north gate first.</p>
    <form id="comment-form" action="/api/social-notes/comments.json" method="post">
      <label for="comment-text">Comment</label>
      <textarea id="comment-text" name="comment">Looks useful</textarea>
      <button id="comment-submit" type="submit">Send</button>
    </form>
  </section>
</article>
""",
        mobile=True,
    )


def _social_notes_security_page() -> str:
    return _page(
        "Social Notes Safety Landing",
        """
<section class="panel" data-testid="social-security-check">
  <h2>Content unavailable</h2>
  <p>This deterministic page mimics a mobile safety landing without real platform content.</p>
  <a href="/scenarios/social-notes">Return to feed</a>
</section>
""",
        mobile=True,
    )


def _note_card(note_id: str, title: str, meta: str, tag: str) -> str:
    return f"""
<article id="{note_id}" class="card note-card" data-testid="note-card-{note_id}" data-tag="{tag}">
  <h3>{title}</h3>
  <p>{meta}</p>
  <a data-testid="note-link-{note_id}" href="/scenarios/social-notes/note/{note_id}">Open note</a>
</article>
"""


def _timeline_page() -> str:
    return _page(
        "Mock Timeline",
        """
<form id="timeline-composer" data-testid="timeline-composer" action="/api/timeline/posts.json" method="post">
  <label for="post-text">What is happening?</label>
  <textarea id="post-text" name="text">Shipping MCP Lab today</textarea>
  <button id="post-submit" data-testid="post-submit" type="submit">Post</button>
</form>
<section id="timeline-feed" data-testid="timeline-feed">
  <article id="post-001" class="card post" data-testid="post-post-001"><h3>Ada</h3><p>Testing deterministic browser agents.</p><button>Reply</button><button>Like</button></article>
  <article id="post-002" class="card post" data-testid="post-post-002"><h3>Grace</h3><p>Structured MCP output beats screenshot guessing.</p><button>Reply</button><button>Like</button></article>
</section>
<button id="load-more-posts" data-testid="load-more-posts">Load more</button>
<script>
  document.querySelector('#load-more-posts').addEventListener('click', () => {
    const item = document.createElement('article');
    item.id = 'post-003';
    item.className = 'card post';
    item.dataset.testid = 'post-post-003';
    item.innerHTML = '<h3>Katherine</h3><p>New deterministic post appended.</p><button>Reply</button><button>Like</button>';
    document.querySelector('#timeline-feed').appendChild(item);
  });
</script>
""",
    )


def _commerce_products_json() -> str:
    return json.dumps(
        {
            "items": [
                {"id": "aurora-headphones", "name": "Aurora Headphones", "price": 399},
                {"id": "travel-keyboard", "name": "Travel Keyboard", "price": 259},
                {"id": "creator-light", "name": "Creator Light", "price": 189},
            ]
        },
        ensure_ascii=False,
    )


def _social_notes_feed_json() -> str:
    return json.dumps(
        {
            "items": [
                {"id": "note-001", "title": "City coffee map"},
                {"id": "note-002", "title": "Weekend market guide"},
            ]
        },
        ensure_ascii=False,
    )


def _timeline_posts_json() -> str:
    return json.dumps(
        {
            "items": [
                {"id": "post-001", "author": "Ada"},
                {"id": "post-002", "author": "Grace"},
            ]
        },
        ensure_ascii=False,
    )


def _protected_json() -> str:
    return json.dumps(
        {
            "ok": False,
            "status": 403,
            "message": "Synthetic challenge page. Use recovery flow.",
        },
        ensure_ascii=False,
    )


def _not_found_page(path: str) -> str:
    return _page(
        "MCP Lab 404",
        f"""
<section class="panel" data-testid="not-found">
  <h2>Route not found</h2>
  <p>{path}</p>
  <a href="/">Return home</a>
</section>
""",
    )
