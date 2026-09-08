"""Verify read-only scenario import against real SIM/FEM objects through MCP."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    env = dict(os.environ)
    env.update(
        PYTHONPATH=r"C:\ProgramData\BasementHypervisor\nx-mcp-simcenter\source\src",
        NX_MCP_ENABLE_SIMCENTER="1",
        NX_MCP_ENABLE_EXPERIMENTAL="1",
        NX_MCP_WORKSPACE=r"D:\CAD\SIMCENTER_MCP_WORKSPACE",
        NX_MCP_BRIDGE_DESCRIPTOR=r"C:\Users\cadadmin\AppData\Local\nx-mcp\simcenter-bridge.json",
        NX_MCP_SURFACE="full",
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "nx_mcp.server"], env=env
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()
        stage = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
        results = {}

        async def call(key, method, args):
            result = await client.call_tool(method, args)
            results[key] = result.model_dump(mode="json")
            (stage / "stdio-fem-close.json").write_text(
                json.dumps(
                    {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": results},
                    indent=2,
                )
            )
            return result

        docs = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        target = next(d for d in docs if d["path"].endswith("public_open_fem_r2.fem"))
        assert not target["work"]
        other_flags = {d["path"]: d["modified"] for d in docs if d != target}
        document = target["document"]["id"]
        saved = await call(
            "saved", "nx_sim_save", {"document": document, "operation_id": "fem-close-save-r1"}
        )
        assert not saved.isError, saved.structuredContent
        args = {"document": document, "operation_id": "fem-close-clean-r1"}
        closed = await call("closed", "nx_sim_close", args)
        assert not closed.isError, closed.structuredContent
        assert any(p["id"] == document for p in closed.structuredContent["closed_parts"])
        replay = await call("replay", "nx_sim_close", args)
        assert not replay.isError, replay.structuredContent
        assert replay.structuredContent["closed_parts"] == closed.structuredContent["closed_parts"]
        stale = await call(
            "stale", "nx_sim_activate", {"document": document, "operation_id": "fem-close-stale-r1"}
        )
        assert stale.isError and stale.structuredContent["code"] == "NX_OBJECT_STALE", (
            stale.structuredContent
        )
        reopened = await call(
            "reopened",
            "nx_sim_open",
            {"path": target["path"], "operation_id": "fem-close-reopen-r1"},
        )
        assert not reopened.isError and not reopened.structuredContent["already_loaded"], (
            reopened.structuredContent
        )
        assert reopened.structuredContent["document"]["id"] != document
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        assert {d["path"]: d["modified"] for d in after if d["path"] in other_flags} == other_flags
        results["other_flags_preserved"] = True
        (stage / "stdio-fem-close.json").write_text(
            json.dumps(
                {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": results},
                indent=2,
            )
        )
        print(
            "Native MCP inactive FEM save/close/retry/stale-reference rejection and reopen passed"
        )


asyncio.run(main())
