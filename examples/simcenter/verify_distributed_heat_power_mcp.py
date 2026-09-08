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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-distributed-heat-power.json")
        responses = {}

        async def call(key, name, args, error=False):
            r = await client.call_tool(name, args)
            responses[key] = r.model_dump(mode="json")
            output.write_text(json.dumps(responses, indent=2))
            assert bool(r.isError) == error, r
            return r.structuredContent

        schemas = await client.list_tools()
        assert any(t.name == "nx_sim_distributed_heat" for t in schemas.tools)
        await call(
            "create",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/distributed-heat-public-20260908-r2",
                "length_mm": 10,
                "block_origins_mm": [[0, 0, 0], [20, 0, 0]],
                "operation_id": "distributed-heat-create-r2",
            },
        )
        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        row = next(d for d in docs["documents"] if d["work"] and d["document_type"] == "SimPart")
        doc, path = row["document"]["id"], row["path"]
        inv = await call("faces", "nx_sim_faces", {"document": doc})
        first = inv["faces"][0]
        other = next(f for f in inv["faces"] if f["body"]["id"] != first["body"]["id"])
        common = {
            "document": doc,
            "name": "MCP surface flux",
            "provenance": "assumed native public-tool benchmark",
            "kind": "surface_flux",
            "value": 10000.0,
        }
        await call(
            "wrong_kind",
            "nx_sim_distributed_heat",
            {
                **common,
                "targets": [first["body"]["id"]],
                "operation_id": "distributed-heat-wrong-kind-r2",
            },
            error=True,
        )
        args = {
            **common,
            "targets": [first["face"]["id"]],
            "operation_id": "distributed-heat-flux-r2",
        }
        flux = await call("flux", "nx_sim_distributed_heat", args)
        replay = await call("replay", "nx_sim_distributed_heat", args)
        assert flux["load"]["id"] == replay["load"]["id"]
        assert flux["value"] == 10000 and flux["units"] == "W/m^2"
        assert abs(flux["total_power_w"] - 1.0) < 1e-12
        await call(
            "duplicate",
            "nx_sim_distributed_heat",
            {**args, "name": "MCP duplicate", "operation_id": "distributed-heat-duplicate-r2"},
            error=True,
        )
        volume = await call(
            "volume",
            "nx_sim_distributed_heat",
            {
                **common,
                "kind": "volume_generation",
                "value": 100000.0,
                "name": "MCP volume generation",
                "targets": [other["body"]["id"]],
                "operation_id": "distributed-heat-volume-r2",
            },
        )
        assert volume["value"] == 100000 and volume["units"] == "W/m^3"
        assert abs(volume["total_power_w"] - 0.1) < 1e-12
        await call(
            "save", "nx_sim_save", {"document": doc, "operation_id": "distributed-heat-save-r2"}
        )
        await call(
            "close", "nx_sim_close", {"document": doc, "operation_id": "distributed-heat-close-r2"}
        )
        await call(
            "open", "nx_sim_open", {"path": path, "operation_id": "distributed-heat-open-r2"}
        )
        docs = await call("reopened_documents", "nx_sim_documents", {"limit": 100})
        current = next(
            d["document"]["id"] for d in docs["documents"] if d["work"] and d["path"] == path
        )
        assert current != doc
        loads = await call(
            "persisted",
            "nx_sim_loads",
            {"document": current, "include_properties": True, "include_targets": True},
        )
        assert loads["total"] == 2 and loads["next_offset"] is None
        for key, prop_name, symbol in (
            ("flux", "Heat Flux", "W/m^2"),
            ("volume", "Heat Generation", "W/m^3"),
        ):
            original = responses[key]["structuredContent"]
            row = next(r for r in loads["loads"] if r["load"]["name"] == original["load"]["name"])
            prop = next(p for p in row["properties"] if p["name"] == prop_name)
            assert float(prop["expression"]) == original["value"] and prop["unit_symbol"] == symbol
            assert row["provenance"] == original["provenance"]
            assert row["energy_accounting"] == "internal_heat"
            target = row["target_sets"][0]
            assert target["count"] == 1 and not target["truncated"]
            ref_kind = "face" if key == "flux" else "body"
            assert (
                target["members"][0][ref_kind]["journal_id"] == original["targets"][0]["journal_id"]
            )
        await call("stale_document", "nx_sim_loads", {"document": doc}, error=True)
        print(
            "Public distributed heat created, replayed, saved and reopened; inspect persisted readback receipt"
        )


asyncio.run(main())
