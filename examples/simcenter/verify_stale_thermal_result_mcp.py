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
        output = Path(
            r"Z:\nx-mcp-integration\simcenter-discovery\stdio-stale-thermal-result-r2.json"
        )

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        rows = docs.structuredContent["documents"]
        fem = next(d for d in rows if d["path"].endswith("OrthoZR1_mesh.fem"))
        sim = next(d for d in rows if d["path"].endswith("live_revision_solve_r1.sim"))
        document, simulation = fem["document"]["id"], sim["document"]["id"]
        query = {"document": simulation, "job_id": "live-revision-thermal-01"}
        activated = await call(
            "activate_before",
            "nx_sim_activate",
            {"document": simulation, "operation_id": "stale-audit-activate-before-r2"},
        )
        assert not activated.isError
        baseline = await call("baseline", "nx_sim_result_identity", query)
        assert not baseline.isError, baseline.structuredContent
        assert baseline.structuredContent["job_binding"]["live_thermal_state"]["state"] == "matches"
        inspected = await call("collector_before", "nx_sim_collectors", {"document": document})
        before = inspected.structuredContent["collectors"][0]
        original = before["orientation"]["stored_frame"]
        args = {
            "document": document,
            "collector": before["collector"]["id"],
            "expected_state_sha256": before["state_sha256"],
            "origin_mm": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "operation_id": "stale-audit-frame-change-r2",
        }
        changed = await call("changed", "nx_sim_material_frame", args)
        assert not changed.isError, changed.structuredContent
        after = changed.structuredContent["collector_state"]
        try:
            activated = await call(
                "activate_changed",
                "nx_sim_activate",
                {"document": simulation, "operation_id": "stale-audit-activate-changed-r2"},
            )
            assert not activated.isError
            stale = await call("stale_result", "nx_sim_result_identity", query)
        finally:
            restored = await call(
                "restored_frame",
                "nx_sim_material_frame",
                {
                    **args,
                    "expected_state_sha256": after["state_sha256"],
                    "origin_mm": original["origin"],
                    "x_axis": original["axes_in_part_absolute"][0],
                    "y_axis": original["axes_in_part_absolute"][1],
                    "operation_id": "stale-audit-frame-restore-r2",
                },
            )
            assert not restored.isError, restored.structuredContent
            activated = await call(
                "activate_restored",
                "nx_sim_activate",
                {"document": simulation, "operation_id": "stale-audit-activate-restored-r2"},
            )
            assert not activated.isError
        assert not stale.isError, stale.structuredContent
        assert stale.structuredContent["result_freshness"] == "stale"
        binding = stale.structuredContent["job_binding"]
        assert binding["model_result_freshness"] == "stale"
        assert binding["associated_result_matches_observed_artifact"]
        assert binding["live_thermal_state"]["state"] == "changed"
        final = await call("final_audit", "nx_sim_result_identity", query)
        assert not final.isError, final.structuredContent
        assert final.structuredContent["job_binding"]["live_thermal_state"]["state"] == "matches"
        assert final.structuredContent["job_binding"]["model_result_freshness"] == "not_verified"
        output.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "responses": responses,
                    "solver_launched": False,
                    "saved": False,
                },
                indent=2,
            )
        )
        print(
            "Native post-solve frame change marked existing result stale; restored axes matched again without claiming full freshness"
        )


asyncio.run(main())
