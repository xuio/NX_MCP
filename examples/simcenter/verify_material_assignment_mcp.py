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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-material-assignment.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        fem = next(
            d
            for d in docs.structuredContent["documents"]
            if d["path"].endswith("OrthoZR1_mesh.fem")
        )
        document = fem["document"]["id"]
        materials = await call(
            "materials", "nx_sim_materials", {"document": document, "limit": 100}
        )
        alternate = next(
            r["material"]
            for r in materials.structuredContent["materials"]
            if r["material"]["name"] == "BENCHMARK_K200"
        )
        inspected = await call("before", "nx_sim_collectors", {"document": document})
        before = inspected.structuredContent["collectors"][0]
        assert before["material"]["name"] == "ORTHOTROPIC_STUDY_12_7_04"
        args = {
            "document": document,
            "collector": before["collector"]["id"],
            "material": alternate["id"],
            "expected_state_sha256": before["state_sha256"],
            "operation_id": "material-assignment-public-r1",
        }
        changed = await call("assigned", "nx_sim_assign_material", args)
        assert not changed.isError, changed.structuredContent
        after = changed.structuredContent["collector_state"]
        assert after["material"]["id"] == alternate["id"]
        assert after["orientation"] == before["orientation"]
        replay = await call("replay", "nx_sim_assign_material", args)
        assert not replay.isError and replay.structuredContent["collector_state"] == after
        stale = await call(
            "stale",
            "nx_sim_assign_material",
            {**args, "operation_id": "material-assignment-stale-r1"},
        )
        assert stale.isError and stale.structuredContent["code"] == "NX_SIM_REVISION_MISMATCH"
        restored = await call(
            "restored",
            "nx_sim_assign_material",
            {
                **args,
                "material": before["material"]["id"],
                "expected_state_sha256": after["state_sha256"],
                "operation_id": "material-assignment-restore-r1",
            },
        )
        assert not restored.isError, restored.structuredContent
        assert restored.structuredContent["collector_state"] == before
        final_docs = await call("final_documents", "nx_sim_documents", {"limit": 100})
        assert not final_docs.isError
        output.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "responses": responses,
                    "saved": False,
                    "results_revalidated": False,
                },
                indent=2,
            )
        )
        print(
            "Material MCP assignment, replay, stale-state rejection and original assignment restoration passed"
        )


asyncio.run(main())
