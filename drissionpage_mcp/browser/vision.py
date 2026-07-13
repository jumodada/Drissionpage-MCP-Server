"""Autonomous visual interaction orchestration for browser tabs."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tab import PageTab
    from .pointer import PointerButton, PointerProfile

_DEFAULT_KEYWORDS = (
    "turnstile",
    "recaptcha",
    "hcaptcha",
    "challenges.cloudflare.com",
    "g-recaptcha",
)


class VisionOperations:
    """Own bounded detection, batch actions, and observable result polling."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def detect_challenges(
        self, keywords: list[str] | None = None
    ) -> dict[str, Any]:
        normalized = [
            item.strip().lower()
            for item in (keywords or _DEFAULT_KEYWORDS)
            if item.strip()
        ]
        result = self._page.run_js(
            _challenge_detection_script(normalized), as_expr=True
        )
        if not isinstance(result, dict):
            raise RuntimeError("challenge detection script returned an invalid payload")
        signals = list(result.get("signals") or [])[:100]
        providers = sorted(
            {
                str(signal.get("provider_hint", "unknown"))
                for signal in signals
                if signal.get("provider_hint")
            }
        )
        return {
            "detected": bool(signals),
            "challenge_types": providers,
            "signals": signals,
            "iframes": list(result.get("iframes") or [])[:50],
            "page_state": {"url": self._tab.url, "title": self._tab.title},
            "suggestions": _challenge_suggestions(bool(signals)),
        }

    async def click_batch(
        self,
        targets: list[dict[str, Any]],
        *,
        profile: "PointerProfile",
        button: "PointerButton",
        delay_min_ms: int,
        delay_max_ms: int,
        continue_on_error: bool,
        stop_on_url_change: bool,
    ) -> dict[str, Any]:
        initial_url = self._tab.url
        results: list[dict[str, Any]] = []
        aborted = False
        abort_index: int | None = None
        for index, target in enumerate(targets):
            if stop_on_url_change and self._tab.url != initial_url:
                aborted = True
                abort_index = index
                break
            try:
                motion = await self._tab.pointer.click_at(
                    float(target["x"]),
                    float(target["y"]),
                    profile=profile,
                    button=button,
                )
                results.append(
                    {
                        "index": index,
                        "x": float(target["x"]),
                        "y": float(target["y"]),
                        "label": str(target.get("label", "")),
                        "success": True,
                        "error": None,
                        "motion": motion.to_dict(),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "index": index,
                        "x": float(target["x"]),
                        "y": float(target["y"]),
                        "label": str(target.get("label", "")),
                        "success": False,
                        "error": str(exc),
                        "motion": None,
                    }
                )
                if not continue_on_error:
                    aborted = True
                    abort_index = index
                    break
            if index < len(targets) - 1:
                delay = self._tab.pointer.random_delay(delay_min_ms, delay_max_ms)
                if delay:
                    await asyncio.sleep(delay)
        return {
            "total_targets": len(targets),
            "clicks_completed": sum(item["success"] for item in results),
            "results": results,
            "aborted": aborted,
            "abort_index": abort_index,
            "initial_url": initial_url,
            "final_url": self._tab.url,
        }

    async def wait_challenge_result(
        self,
        *,
        timeout_s: float,
        poll_interval_s: float,
        token_selectors: list[str],
        success_selectors: list[str],
        retry_selectors: list[str],
        challenge_selectors: list[str],
    ) -> dict[str, Any]:
        start = time.monotonic()
        deadline = start + timeout_s
        observations = 0
        initial_fingerprint = ""
        last: dict[str, Any] = {}
        while True:
            observations += 1
            result = self._page.run_js(
                _challenge_result_script(
                    token_selectors,
                    success_selectors,
                    retry_selectors,
                    challenge_selectors,
                ),
                as_expr=True,
            )
            if not isinstance(result, dict):
                raise RuntimeError(
                    "challenge result script returned an invalid payload"
                )
            last = result
            fingerprint = str(result.get("challenge_fingerprint", ""))
            if not initial_fingerprint:
                initial_fingerprint = fingerprint
            status = _classify_challenge_result(result, initial_fingerprint)
            if status in {"passed", "needs_retry", "new_challenge", "indeterminate"}:
                return _challenge_wait_payload(status, result, start, observations)
            if time.monotonic() >= deadline:
                terminal = (
                    "timeout" if last.get("observable_signals") else "indeterminate"
                )
                return _challenge_wait_payload(terminal, last, start, observations)
            await asyncio.sleep(poll_interval_s)


def _challenge_suggestions(detected: bool) -> list[str]:
    if not detected:
        return [
            "No known verification signals were detected; continue the ordinary selector-first workflow."
        ]
    return [
        "Capture a fresh viewport screenshot with full_page=false before coordinate actions.",
        "Use page_pointer_move, page_click_xy, page_click_xy_batch, or page_pointer_drag according to interaction intent.",
        "Poll observable state with page_wait_challenge_result or wait_until after the action.",
        "On retry, collect fresh evidence and recompute coordinates instead of reusing stale positions.",
        "Use only in authorized testing or technical research; automated verification completion is not recommended or guaranteed.",
    ]


def _classify_challenge_result(result: dict[str, Any], initial: str) -> str:
    if int(result.get("token_length", 0)) > 0 or result.get("success_selector"):
        return "passed"
    if result.get("retry_selector"):
        return "needs_retry"
    fingerprint = str(result.get("challenge_fingerprint", ""))
    if initial and fingerprint and fingerprint != initial:
        return "new_challenge"
    return "pending"


def _challenge_wait_payload(
    status: str, result: dict[str, Any], start: float, observations: int
) -> dict[str, Any]:
    return {
        "status": status,
        "passed": status == "passed",
        "needs_retry": status == "needs_retry",
        "new_challenge": status == "new_challenge",
        "token_present": int(result.get("token_length", 0)) > 0,
        "token_length": int(result.get("token_length", 0)),
        "matched_selector": str(
            result.get("success_selector")
            or result.get("retry_selector")
            or result.get("challenge_selector")
            or ""
        ),
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "observations": observations,
    }


def _challenge_detection_script(keywords: list[str]) -> str:
    return f"""(() => {{
      const keywords = {json.dumps(keywords)};
      const lower = value => String(value || '').toLowerCase();
      const roots = [];
      const visit = root => {{
        roots.push(root);
        for (const element of root.querySelectorAll('*')) {{
          if (element.shadowRoot) visit(element.shadowRoot);
        }}
      }};
      visit(document);
      const queryAll = selector => roots.flatMap(root => Array.from(root.querySelectorAll(selector)));
      const queryOne = selector => queryAll(selector)[0] || null;
      const provider = value => {{
        const text = lower(value);
        if (text.includes('turnstile') || text.includes('cloudflare')) return 'turnstile';
        if (text.includes('recaptcha') || text.includes('g-recaptcha')) return 'recaptcha';
        if (text.includes('hcaptcha') || text.includes('h-captcha')) return 'hcaptcha';
        return 'unknown';
      }};
      const signals = [];
      const iframes = queryAll('iframe').map((frame, index) => {{
        const haystack = [frame.src, frame.title, frame.name, frame.id, frame.className].join(' ');
        const matched = keywords.filter(keyword => lower(haystack).includes(keyword));
        if (matched.length) signals.push({{source:'iframe', provider_hint:provider(haystack), matched_signal:matched[0], frame_index:index}});
        return {{index, src:String(frame.src || ''), title:String(frame.title || ''), matched_keywords:matched}};
      }});
      const selectors = ['.cf-turnstile','.g-recaptcha','.h-captcha','[data-sitekey]','input[name="cf-turnstile-response"]','textarea[name="g-recaptcha-response"]','textarea[name="h-captcha-response"]'];
      for (const selector of selectors) {{
        const element = queryOne(selector);
        if (element) signals.push({{source:element.getRootNode() instanceof ShadowRoot ? 'shadow-dom' : 'dom', provider_hint:provider(selector), matched_signal:selector, frame_index:null}});
      }}
      for (const script of queryAll('script')) {{
        const matched = keywords.find(keyword => lower(script.src).includes(keyword));
        if (matched) signals.push({{source:'script', provider_hint:provider(script.src), matched_signal:matched, frame_index:null}});
      }}
      return {{signals, iframes, shadow_root_count:Math.max(0, roots.length - 1)}};
    }})()"""


def _challenge_result_script(
    token_selectors: list[str],
    success_selectors: list[str],
    retry_selectors: list[str],
    challenge_selectors: list[str],
) -> str:
    return f"""(() => {{
      const roots = [];
      const visit = root => {{
        roots.push(root);
        for (const element of root.querySelectorAll('*')) {{
          if (element.shadowRoot) visit(element.shadowRoot);
        }}
      }};
      visit(document);
      const queryOne = selector => {{
        for (const root of roots) {{
          const element = root.querySelector(selector);
          if (element) return element;
        }}
        return null;
      }};
      const first = selectors => selectors.find(selector => queryOne(selector)) || '';
      let tokenLength = 0;
      for (const selector of {json.dumps(token_selectors)}) {{
        const element = queryOne(selector);
        const value = element ? String(element.value || element.textContent || '') : '';
        tokenLength = Math.max(tokenLength, value.length);
      }}
      const successSelector = first({json.dumps(success_selectors)});
      const retrySelector = first({json.dumps(retry_selectors)});
      const challengeSelector = first({json.dumps(challenge_selectors)});
      const frames = roots.flatMap(root => Array.from(root.querySelectorAll('iframe'))).map(frame => String(frame.src || '')).sort();
      return {{
        token_length: tokenLength,
        success_selector: successSelector,
        retry_selector: retrySelector,
        challenge_selector: challengeSelector,
        challenge_present: Boolean(challengeSelector || frames.length),
        challenge_fingerprint: JSON.stringify([challengeSelector, frames, roots.length]),
        observable_signals: Boolean(tokenLength || successSelector || retrySelector || challengeSelector || frames.length),
      }};
    }})()"""
