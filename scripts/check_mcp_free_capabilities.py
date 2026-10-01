#!/usr/bin/env python3
"""Verify connectivity and FREE catalog/field capabilities of the configured MCP services.

Read-only acceptance for T03-L. Uses the endpoints/keys from the official
clone's gitignored ``.env`` (via ``scripts/gen_mcp_json.py``'s loader) without
ever printing or persisting secret values. Only free operations are exercised:

- ``event_tool``: ``GET <host>/healthz`` plus MCP ``initialize``/``tools/list``.
  The structured data calls (``get_data`` / ``get_source_detail``) are billed
  per call and are NOT invoked.
- ``user_pool_survey_mcp``: MCP ``initialize``/``tools/list`` plus the free
  read-only tools documented in ``resources/capabilities.yaml``
  (``get_user_pool_simulation_capabilities``, ``list_user_pool_platforms``,
  ``match_user_pool_fields``). The metered simulation call
  (``run_user_pool_distribution_simulation``) is NOT invoked.

Redacted raw replies are archived under ``data/raw/mcp_checks/<date>/``
(gitignored) for provenance. The console summary shows server names, tool
names and response field structure only — no endpoints, no keys.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_REPO = REPO_ROOT.parent / "socioverse2_repo"
ARCHIVE_DIR = REPO_ROOT / "data" / "raw" / "mcp_checks" / datetime.now().strftime("%Y-%m-%d")
TIMEOUT = 30

sys.path.insert(0, str(OFFICIAL_REPO / "scripts"))
import gen_mcp_json  # noqa: E402  (official loader: process env, then .env lookup)

SENSITIVE_KEY = re.compile(r"(key|token|secret|authorization|credential|password)", re.I)
PAID_OR_UNSAFE = {"get_data", "get_source_detail", "run_user_pool_distribution_simulation"}

FREE_PROBES = {
    "user_pool_survey_mcp": [
        ("get_user_pool_simulation_capabilities", {}),
        ("list_user_pool_platforms", {}),
        ("match_user_pool_fields", {
            "fields": ["age", "gender", "income", "education", "region", "race"],
        }),
    ],
    "event_tool": [  # healthz + free catalog only; structured calls are billed
        ("list_sources", {}),
    ],
}


def redact(obj):
    """Recursively blank values whose field name looks sensitive."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if SENSITIVE_KEY.search(str(k)) else redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def shape(obj, depth: int = 0):
    """Structure-only summary of a JSON value (types/keys, no payload values)."""
    if depth > 2:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {str(k): shape(v, depth + 1) for k, v in list(obj.items())[:20]}
    if isinstance(obj, list):
        return [shape(obj[0], depth + 1), f"...({len(obj)} items)"] if obj else []
    return type(obj).__name__


class McpHttpClient:
    """Minimal streamable-HTTP JSON-RPC client (stdlib only), mirroring the
    Accept/Authorization pattern of socioverse.external_events._http_json."""

    def __init__(self, url: str, key: str | None):
        self.url = url
        self.key = key
        self.session_id: str | None = None
        self._rpc_id = 0

    def _request(self, payload: dict | None, method: str = "POST",
                 url: str | None = None) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url or self.url, data=data, headers=headers,
                                     method=method)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            meta = {"status": resp.status,
                    "content_type": resp.headers.get("Content-Type", ""),
                    "session_id": resp.headers.get("Mcp-Session-Id")}
        if meta["session_id"] and not self.session_id:
            self.session_id = meta["session_id"]
        if "text/event-stream" in meta["content_type"]:
            for line in body.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    break
        return (json.loads(body) if body.strip() else {}), meta

    def get(self, url: str) -> tuple[dict, dict]:
        return self._request(None, method="GET", url=url)

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self._rpc_id += 1
        resp, _ = self._request({"jsonrpc": "2.0", "id": self._rpc_id,
                                 "method": method, "params": params or {}})
        if resp.get("error"):
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp.get("result") or {}

    def initialize(self) -> dict:
        result = self.rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "sce-t03l-acceptance", "version": "0.1"},
        })
        # stateless servers tolerate a missing notifications/initialized
        try:
            self._request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:
            pass
        return result

    def list_tools(self) -> list[dict]:
        return self.rpc("tools/list").get("tools") or []

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""
        if result.get("isError"):
            raise RuntimeError(f"tool error: {text[:300]}")
        try:
            return json.loads(text)
        except ValueError:
            return {"_raw_text": text[:2000]}


def check_server(name: str, env: dict) -> dict:
    url_var, key_var = gen_mcp_json.SERVICES[name]
    url = (env.get(url_var) or "").strip()
    record = {"server": name, "checked_at": datetime.now(timezone.utc).isoformat(),
              "url_configured": bool(url), "key_configured": bool((env.get(key_var) or "").strip()),
              "host": urllib.parse.urlsplit(url).netloc if url else None}
    if not url:
        record["status"] = "skipped: URL not configured"
        return record
    client = McpHttpClient(url, (env.get(key_var) or "").strip() or None)
    try:
        if name == "event_tool":
            parts = urllib.parse.urlsplit(url)
            health, _ = client.get(f"{parts.scheme}://{parts.netloc}/healthz")
            record["healthz"] = redact(health)
        init = client.initialize()
        record["initialize"] = redact({
            "protocolVersion": init.get("protocolVersion"),
            "serverInfo": init.get("serverInfo"),
        })
        tools = client.list_tools()
        record["tools"] = [
            {"name": t.get("name"),
             "input_fields": sorted((t.get("inputSchema") or {}).get("properties") or {})}
            for t in tools
        ]
        tool_names = {t.get("name") for t in tools}
        record["paid_tools_present_not_called"] = sorted(tool_names & PAID_OR_UNSAFE)
        probes = []
        for tool, args in FREE_PROBES.get(name, []):
            if tool not in tool_names:
                probes.append({"tool": tool, "status": "not advertised"})
                continue
            try:
                reply = client.call_tool(tool, args)
                probes.append({"tool": tool, "status": "ok",
                               "response_shape": shape(reply), "response": redact(reply)})
            except Exception as exc:  # noqa: BLE001 - record and continue
                probes.append({"tool": tool, "status": f"error: {type(exc).__name__}: {exc}"})
        record["free_probes"] = probes
        record["status"] = "ok"
    except urllib.error.HTTPError as exc:
        record["status"] = f"http_error: {exc.code}"
        if exc.code in (401, 403):
            record["hint"] = "server rejected the configured key"
    except Exception as exc:  # noqa: BLE001 - acceptance script reports, not raises
        record["status"] = f"error: {type(exc).__name__}: {exc}"
    return record


def main() -> int:
    env = gen_mcp_json.load_env()
    print("env configured (values never printed): "
          + ", ".join(f"{v}={'set' if (env.get(v) or '').strip() else 'unset'}"
                      for pair in gen_mcp_json.SERVICES.values() for v in pair))
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    for name in gen_mcp_json.SERVICES:
        record = check_server(name, env)
        out = ARCHIVE_DIR / f"{name}.json"
        out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"\n[{name}] {record['status']}")
        for t in record.get("tools") or []:
            print(f"  tool: {t['name']}  args: {', '.join(t['input_fields']) or '-'}")
        for p in record.get("free_probes") or []:
            print(f"  free probe {p['tool']}: {p['status']}")
        if record.get("paid_tools_present_not_called"):
            print(f"  paid tools present, NOT called: "
                  f"{', '.join(record['paid_tools_present_not_called'])}")
        print(f"  archived (redacted): {out}")
        ok = ok and str(record["status"]).startswith("ok")
    print(f"\narchive dir: {ARCHIVE_DIR} (gitignored)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
