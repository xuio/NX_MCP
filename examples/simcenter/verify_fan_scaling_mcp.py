"""Verify orthotropic material schema, native creation and operation replay."""

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
        responses = {}
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-fan-scaling.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        source = next(
            d
            for d in docs.structuredContent["documents"]
            if d["path"].endswith("benchmark_9c5a613280cc_analysis.sim")
        )
        activated = await call(
            "activate",
            "nx_sim_activate",
            {"document": source["document"]["id"], "operation_id": "fan-scale-activate-r1"},
        )
        assert not activated.isError
        path = "ui-benchmarks/fan-scaling-public-20260908-r1/fan_scaling_public_r1.sim"
        copied = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": source["document"]["id"],
                "path": path,
                "operation_id": "fan-scale-copy-r1",
            },
        )
        assert not copied.isError, copied.structuredContent
        document = copied.structuredContent["document"]["id"]
        tables = await call(
            "tables", "nx_sim_fan_tables", {"document": document, "include_samples": True}
        )
        original = next(
            t
            for t in tables.structuredContent["tables"]
            if t["manifest"]["name"] == "Retained synthetic fan"
        )
        args = {
            "document": document,
            "source_field": original["field"]["id"],
            "name": "Derived 1100 RPM",
            "rpm": 1100,
            "operation_id": "fan-scale-create-r1",
        }
        bad = await call(
            "range_rejected",
            "nx_sim_scale_fan_table",
            {**args, "rpm": 1300, "operation_id": "fan-scale-range-r1"},
        )
        assert bad.isError and bad.structuredContent["code"] == "NX_INVALID_ARGUMENT"
        created = await call("created", "nx_sim_scale_fan_table", args)
        assert not created.isError, created.structuredContent
        manifest = created.structuredContent["manifest"]
        assert manifest["provenance"]["kind"] == "assumed"
        assert abs(manifest["points"][0]["pressure_Pa"] - 1.21) < 1e-12
        replay = await call("replay", "nx_sim_scale_fan_table", args)
        assert (
            not replay.isError
            and replay.structuredContent["field"] == created.structuredContent["field"]
        )
        saved = await call(
            "save", "nx_sim_save", {"document": document, "operation_id": "fan-scale-save-r1"}
        )
        assert not saved.isError, saved.structuredContent
        closed = await call(
            "close", "nx_sim_close", {"document": document, "operation_id": "fan-scale-close-r1"}
        )
        assert not closed.isError, closed.structuredContent
        opened = await call(
            "reopen", "nx_sim_open", {"path": path, "operation_id": "fan-scale-reopen-r1"}
        )
        assert not opened.isError, opened.structuredContent
        new_document = opened.structuredContent["document"]["id"]
        assert new_document != document
        restored = await call(
            "readback",
            "nx_sim_fan_tables",
            {"document": new_document, "include_samples": True, "limit": 100},
        )
        assert not restored.isError, restored.structuredContent
        rows = restored.structuredContent["tables"]
        derived = [t for t in rows if t["manifest"]["name"] == manifest["name"]]
        assert len(derived) == 1 and derived[0]["manifest"] == manifest
        old = next(t for t in rows if t["manifest"]["name"] == original["manifest"]["name"])
        assert old["manifest"] == original["manifest"]
        stale = await call("stale_reference", "nx_sim_fan_tables", {"document": document})
        assert stale.isError
        output.write_text(
            json.dumps(
                {"status": "passed", "responses": responses, "solver_launched": False}, indent=2
            )
        )
        print(
            "Fan scaling range rejection, creation, replay, save/reopen and source preservation passed"
        )


asyncio.run(main())
