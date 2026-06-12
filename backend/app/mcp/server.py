"""
Travel MCP Server — separate process.

Tools (read-only, estimates only):
  - search_hotels
  - search_activities
  - estimate_transport
  - get_destination_facts

Run: python -m app.mcp.server
Docker: docker compose --profile mcp run mcp
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.services.travel_tools import (
    estimate_transport,
    get_destination_facts,
    search_activities,
    search_hotels,
)

TOOLS = [
    {
        "name": "search_hotels",
        "description": "Search hotel estimates (read-only, no booking)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "budget_per_night": {"type": "number"},
                "dates": {"type": "string"},
            },
            "required": ["destination", "budget_per_night"],
        },
    },
    {
        "name": "search_activities",
        "description": "Search activity estimates (read-only)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "interests": {"type": "array", "items": {"type": "string"}},
                "budget": {"type": "number"},
            },
            "required": ["destination", "interests", "budget"],
        },
    },
    {
        "name": "estimate_transport",
        "description": "Estimate transport costs for a trip",
        "inputSchema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "days": {"type": "integer"},
            },
            "required": ["destination", "days"],
        },
    },
    {
        "name": "get_destination_facts",
        "description": "Get destination guide facts",
        "inputSchema": {
            "type": "object",
            "properties": {"destination": {"type": "string"}},
            "required": ["destination"],
        },
    },
]


async def call_tool(name: str, arguments: dict) -> dict:
    if name == "search_hotels":
        result = await search_hotels(
            arguments["destination"],
            arguments["budget_per_night"],
            arguments.get("dates"),
        )
    elif name == "search_activities":
        result = await search_activities(
            arguments["destination"],
            arguments.get("interests", []),
            arguments["budget"],
        )
    elif name == "estimate_transport":
        result = await estimate_transport(
            arguments["destination"], int(arguments["days"])
        )
    elif name == "get_destination_facts":
        result = await get_destination_facts(arguments["destination"])
    else:
        raise ValueError(f"Unknown tool: {name}")
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


async def run_stdio_mcp() -> None:
    """Minimal stdio JSON-RPC loop for M1 (full mcp SDK in M3)."""
    print("Travel MCP server ready (stdio). Tools:", [t["name"] for t in TOOLS], file=sys.stderr)
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
            method = req.get("method")
            if method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"tools": TOOLS}}
            elif method == "tools/call":
                params = req.get("params", {})
                result = await call_tool(params.get("name", ""), params.get("arguments", {}))
                resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": result}
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            print(json.dumps(resp), flush=True)
        except Exception as e:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(e)}}
            print(json.dumps(err), flush=True)


def main() -> None:
    asyncio.run(run_stdio_mcp())


if __name__ == "__main__":
    main()
