"""Read-only MCP verification on the isolated Windows Simcenter installation."""

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
        available = await client.list_tools()
        assert any(t.name == "nx_sim_solutions" for t in available.tools)
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        objects = await client.call_tool("nx_sim_objects", {"document": document})
        assert not objects.isError
        opening = next(
            r["object"]["id"]
            for r in objects.structuredContent["simulation_objects"]
            if r["object"]["name"] == "Duct Opening"
        )
        assert any(
            d["work"] and d["path"].endswith("D-head-loss-mcp-20260908-r1\\head_loss_test_r1.sim")
            for d in docs.structuredContent["documents"]
        )
        results = {}

        async def call(label, **args):
            r = await client.call_tool(
                "nx_sim_head_loss", {"document": document, "opening": opening, **args}
            )
            results[label] = r.model_dump(mode="json")
            Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-head-loss.json").write_text(
                json.dumps(results, indent=2)
            )
            return r

        created = await call(
            "created", coefficient=0, name="Public opening loss", operation_id="head-loss-create-r2"
        )
        assert not created.isError and created.structuredContent["action"] == "created"
        assert created.structuredContent["coefficient"] == 0
        conflict = await call(
            "conflict", coefficient=2, expected_coefficient=3, operation_id="head-loss-conflict-r2"
        )
        assert conflict.isError
        changed = await call(
            "changed", coefficient=2, expected_coefficient=0, operation_id="head-loss-set-r2"
        )
        assert not changed.isError and changed.structuredContent["coefficient"] == 2
        replay = await call(
            "replay", coefficient=2, expected_coefficient=0, operation_id="head-loss-set-r2"
        )
        assert not replay.isError and replay.structuredContent["coefficient"] == 2
        unchanged = await call(
            "unchanged", coefficient=2, expected_coefficient=2, operation_id="head-loss-noop-r2"
        )
        assert not unchanged.isError and unchanged.structuredContent["action"] == "unchanged"
        restored = await call(
            "restored", coefficient=0, expected_coefficient=2, operation_id="head-loss-restore-r2"
        )
        assert not restored.isError and restored.structuredContent["coefficient"] == 0
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        before_flags = {
            d["path"]: d["modified"]
            for d in docs.structuredContent["documents"]
            if d["document"]["id"] != document
        }
        after_flags = {
            d["path"]: d["modified"]
            for d in after.structuredContent["documents"]
            if d["document"]["id"] != document
        }
        assert before_flags == after_flags
        results["other_document_flags_preserved"] = True
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-head-loss.json").write_text(
            json.dumps(results, indent=2)
        )
        print("Native public head-loss update, replay, conflict, no-op and restoration verified")


asyncio.run(main())
