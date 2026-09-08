"""Observe the existing refined flow job, release its gate and audit its log."""

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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-boundary-guard.json")
        responses = {}

        async def call(key, name, args, error=False):
            r = await client.call_tool(name, args)
            responses[key] = r.model_dump(mode="json")
            output.write_text(json.dumps(responses, indent=2))
            assert bool(r.isError) == error, r
            return r.structuredContent

        docs = await call("before", "nx_sim_documents", {"limit": 100})
        source = next(d for d in docs["documents"] if d["path"].endswith("volume_solve_r1.sim"))
        await call(
            "activate",
            "nx_sim_activate",
            {"document": source["document"]["id"], "operation_id": "boundary-guard-activate-r1"},
        )
        copied = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": source["document"]["id"],
                "path": "ui-benchmarks/boundary-guard-20260908-r1/boundary_guard_r1.sim",
                "operation_id": "boundary-guard-copy-r1",
            },
        )
        doc = copied["document"]["id"]
        job = "boundary-guard-r1"
        await call(
            "prepare",
            "nx_sim_prepare_solve",
            {"document": doc, "job_id": job, "operation_id": "boundary-guard-prepare-r1"},
        )
        before = await call(
            "prepared", "nx_sim_job_status", {"job_id": job, "include_manifest": True}
        )
        assert (
            before["state"] == "accepted"
            and before["manifest"]["live_thermal_state"]["adapter"] == 2
        )
        faces = await call("faces", "nx_sim_faces", {"document": doc})
        await call(
            "change",
            "nx_sim_distributed_heat",
            {
                "document": doc,
                "targets": [faces["faces"][0]["face"]["id"]],
                "kind": "surface_flux",
                "value": 100,
                "name": "Post preparation heat change",
                "provenance": "Isolated stale-input rejection test",
                "overlap_policy": "allow_additive",
                "operation_id": "boundary-guard-change-r1",
            },
        )
        rejected = await call(
            "rejected",
            "nx_sim_launch",
            {"document": doc, "job_id": job, "operation_id": "boundary-guard-launch-r1"},
            error=True,
        )
        assert rejected["code"] == "NX_SIM_LIVE_STATE_CHANGED"
        assert rejected["details"]["mutation_outcome"] == "not_started"
        assert rejected["details"]["comparison"]["state"] == "changed"
        after = await call("after", "nx_sim_job_status", {"job_id": job, "include_manifest": True})
        assert after["state"] == "accepted"
        assert before["manifest"] == after["manifest"]
        print(
            "Native prepare -> changed heat -> launch rejected before intent; original job remains accepted"
        )


asyncio.run(main())
