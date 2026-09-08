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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-additive-heat.json")
        responses = {}

        async def call(key, name, args, error=False):
            r = await client.call_tool(name, args)
            responses[key] = r.model_dump(mode="json")
            output.write_text(json.dumps(responses, indent=2))
            assert bool(r.isError) == error, r
            return r.structuredContent

        docs = await call("before", "nx_sim_documents", {"limit": 100})
        source = next(
            d
            for d in docs["documents"]
            if d["work"] and "distributed-heat-public-20260908-r2" in d["path"]
        )
        saved_copy = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": source["document"]["id"],
                "path": "ui-benchmarks/additive-heat-public-20260908-r1/additive_heat_r1.sim",
                "operation_id": "additive-copy-r1",
            },
        )
        doc = saved_copy["document"]["id"]
        faces = (await call("faces", "nx_sim_faces", {"document": doc}))["faces"]
        original = await call(
            "original_loads", "nx_sim_loads", {"document": doc, "include_targets": True}
        )
        flux = next(
            load for load in original["loads"] if load["load"]["name"] == "MCP surface flux"
        )
        face_journal = flux["target_sets"][0]["members"][0]["face"]["journal_id"]
        first = next(f for f in faces if f["face"]["journal_id"] == face_journal)
        other = next(f for f in faces if f["body"]["id"] != first["body"]["id"])
        jobs = [
            (
                "total",
                "nx_sim_heat_power",
                {
                    "document": doc,
                    "body": first["body"]["id"],
                    "power_w": 0.25,
                    "name": "Additional body source",
                    "provenance": "assumed separate internal contribution",
                },
            ),
            (
                "surface",
                "nx_sim_distributed_heat",
                {
                    "document": doc,
                    "targets": [other["face"]["id"]],
                    "kind": "surface_flux",
                    "value": 500,
                    "name": "Additional surface heater",
                    "provenance": "assumed separate surface heater",
                },
            ),
        ]
        for key, tool, args in jobs:
            rejected = await call(
                key + "_rejected",
                tool,
                {**args, "operation_id": "additive-" + key + "-reject-r1"},
                error=True,
            )
            assert rejected["code"] == "NX_SIM_OVERLAPPING_HEAT_SOURCE"
            assert rejected["details"]["mutation_outcome"] == "not_started"
            args.update(
                overlap_policy="allow_additive", operation_id="additive-" + key + "-commit-r1"
            )
            committed = await call(key, tool, args)
            replay = await call(key + "_replay", tool, args)
            assert committed["load"]["id"] == replay["load"]["id"]
            assert committed["overlaps"] and committed["overlap_policy"] == "allow_additive"
        await call("save", "nx_sim_save", {"document": doc, "operation_id": "additive-save-r1"})
        await call("close", "nx_sim_close", {"document": doc, "operation_id": "additive-close-r1"})
        await call(
            "open",
            "nx_sim_open",
            {
                "path": "ui-benchmarks/additive-heat-public-20260908-r1/additive_heat_r1.sim",
                "operation_id": "additive-open-r1",
            },
        )
        docs = await call("reopened", "nx_sim_documents", {"limit": 100})
        current = next(
            d["document"]["id"]
            for d in docs["documents"]
            if d["work"] and d["path"].endswith("additive_heat_r1.sim")
        )
        loads = await call(
            "persisted",
            "nx_sim_loads",
            {"document": current, "include_properties": True, "include_targets": True},
        )
        assert loads["total"] == 4
        for key in ("total", "surface"):
            expected = responses[key]["structuredContent"]
            row = next(r for r in loads["loads"] if r["load"]["name"] == expected["load"]["name"])
            assert (
                row["overlap_policy"] == "allow_additive"
                and row["provenance"] == expected["provenance"]
            )
        print(
            "Both public additive policies, default rejections, replay and persisted policy readback passed"
        )


asyncio.run(main())
