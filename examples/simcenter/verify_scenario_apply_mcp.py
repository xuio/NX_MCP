"""Create an isolated thermal benchmark and apply/save its heat scenario through MCP."""

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
        output = stage / "stdio-scenario-apply.json"
        results = {}

        def record():
            output.write_text(
                json.dumps(
                    {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": results},
                    indent=2,
                )
            )

        async def call(key, method, args):
            result = await client.call_tool(method, args)
            results[key] = result.model_dump(mode="json")
            record()
            return result

        created = await call(
            "created",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/scenario-apply-mcp-20260908-r2",
                "length_mm": 10,
                "operation_id": "scenario-mcp-create-r2",
            },
        )
        assert not created.isError, created.structuredContent
        docs = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        sim = next(d for d in docs if d["work"] and d["document_type"] == "SimPart")
        document = sim["document"]["id"]
        faces = await client.call_tool("nx_sim_faces", {"document": document})
        assert not faces.isError, faces.structuredContent
        args = {
            "document": document,
            "path": "ui-benchmarks/scenario-preview-20260908-r1.csv",
            "region_targets": {"SOC": faces.structuredContent["faces"][0]["body"]["id"]},
            "format": "csv",
            "metadata": {
                "name": "public-scenario-benchmark",
                "workload_revision": "assumed-r1",
                "ambient_K": 298.15,
            },
            "operation_id": "scenario-mcp-apply-r2",
        }
        preview = await call(
            "preview",
            "nx_sim_scenario_preview",
            {k: v for k, v in args.items() if k != "operation_id"},
        )
        assert not preview.isError, preview.structuredContent
        args["expected_preview_sha256"] = preview.structuredContent["preview_sha256"]
        changed = await call(
            "changed",
            "nx_sim_scenario_apply",
            {
                **args,
                "metadata": {**args["metadata"], "ambient_K": 303.15},
                "operation_id": "scenario-mcp-changed-r2",
            },
        )
        assert changed.isError, changed.structuredContent
        assert changed.structuredContent["code"] == "NX_SIM_SCENARIO_CHANGED"
        assert changed.structuredContent["details"]["mutation_outcome"] == "not_started"
        workspace = Path(r"D:\CAD\SIMCENTER_MCP_WORKSPACE")
        changed_file = workspace / "ui-benchmarks/scenario-preview-changed-20260908-r1.csv"
        with changed_file.open("xb") as stream:
            stream.write((workspace / args["path"]).read_bytes() + b"\n")
        changed_bytes = await call(
            "changed_bytes",
            "nx_sim_scenario_apply",
            {**args, "path": str(changed_file), "operation_id": "scenario-mcp-changed-bytes-r2"},
        )
        assert (
            changed_bytes.isError
            and changed_bytes.structuredContent["code"] == "NX_SIM_SCENARIO_CHANGED"
        ), changed_bytes.structuredContent
        untouched = await call("loads_after_rejections", "nx_sim_loads", {"document": document})
        assert not untouched.isError and untouched.structuredContent["total"] == 0

        applied = await call("applied", "nx_sim_scenario_apply", args)
        assert not applied.isError, applied.structuredContent
        assert applied.structuredContent["applied_internal_heat_W"] == 8
        replay = await call("replay", "nx_sim_scenario_apply", args)
        assert not replay.isError, replay.structuredContent
        assert (
            replay.structuredContent["loads"][0]["load"]["id"]
            == applied.structuredContent["loads"][0]["load"]["id"]
        )
        conflict = await call(
            "conflict",
            "nx_sim_scenario_apply",
            {**args, "operation_id": "scenario-mcp-conflict-r2"},
        )
        assert conflict.isError, conflict.structuredContent
        inventory = await call(
            "loads",
            "nx_sim_loads",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert not inventory.isError and inventory.structuredContent["total"] == 1, (
            inventory.structuredContent
        )
        saved = await call(
            "saved", "nx_sim_save", {"document": document, "operation_id": "scenario-mcp-save-r2"}
        )
        assert not saved.isError, saved.structuredContent
        print(
            "Native MCP scenario application, replay, conflict rejection, load readback and save passed"
        )


asyncio.run(main())
