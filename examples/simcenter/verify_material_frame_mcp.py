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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-material-frame.json")

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
        inspected = await call("before", "nx_sim_collectors", {"document": document})
        before = inspected.structuredContent["collectors"][0]
        original = before["orientation"]["stored_frame"]
        assert original["axes_in_part_absolute"] == [
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
        ]
        args = {
            "document": document,
            "collector": before["collector"]["id"],
            "expected_state_sha256": before["state_sha256"],
            "origin_mm": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "operation_id": "frame-public-r1",
        }
        invalid = await call(
            "invalid_axes",
            "nx_sim_material_frame",
            {**args, "y_axis": [1.0, 0.0, 0.0], "operation_id": "frame-invalid-r1"},
        )
        assert invalid.isError and invalid.structuredContent["code"] == "NX_INVALID_ARGUMENT"
        changed = await call("changed", "nx_sim_material_frame", args)
        assert not changed.isError, changed.structuredContent
        after = changed.structuredContent["collector_state"]
        assert after["orientation"]["stored_frame"]["axes_in_part_absolute"] == [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        assert after["material"] == before["material"]
        replay = await call("replay", "nx_sim_material_frame", args)
        assert not replay.isError and replay.structuredContent["collector_state"] == after
        stale = await call(
            "stale", "nx_sim_material_frame", {**args, "operation_id": "frame-stale-r1"}
        )
        assert stale.isError and stale.structuredContent["code"] == "NX_SIM_REVISION_MISMATCH"
        restored = await call(
            "restored",
            "nx_sim_material_frame",
            {
                **args,
                "origin_mm": original["origin"],
                "x_axis": original["axes_in_part_absolute"][0],
                "y_axis": original["axes_in_part_absolute"][1],
                "expected_state_sha256": after["state_sha256"],
                "operation_id": "frame-restore-r1",
            },
        )
        assert not restored.isError, restored.structuredContent
        actual = restored.structuredContent["collector_state"]
        assert actual["material"] == before["material"]
        assert (
            actual["orientation"]["stored_frame"]["axes_in_part_absolute"]
            == original["axes_in_part_absolute"]
        )
        assert actual["orientation"]["stored_frame"]["origin"] == original["origin"]
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
            "Frame MCP edit, invalid axes, replay, stale state and original axes restoration passed"
        )


asyncio.run(main())
