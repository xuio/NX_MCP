"""Verify coupled fan/resistance authoring, replay and persistence; no export or solve."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
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
    receipt = {"responses": {}}
    output = shared / "coupled-fan-public-r1.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        source = "ui-benchmarks/E-finned-material-control-export-20260908-r1/control_export.sim"
        target = "ui-benchmarks/E-coupled-fan-public-20260909-r1/coupled_fan_public_r1.sim"
        if output.exists():
            raise ValueError("Inspect retained receipt before replaying this authoring fixture")
        docs = await call("documents_before", "nx_sim_documents", {"limit": 100})
        initial = {d["path"]: d["modified"] for d in docs["documents"]}
        opened = await call("open", "nx_sim_open", {"path": source})
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        copied = await call(
            "copy",
            "nx_sim_save_as",
            {"document": sid, "path": target, "operation_id": "coupled-fan-copy-r1"},
        )
        assert copied["source_file_unchanged"]
        sid = copied["document"]["id"]
        objects = await call(
            "objects", "nx_sim_objects", {"document": sid, "include_properties": True}
        )
        inlet = next(r for r in objects["simulation_objects"] if r["descriptor"] == "Inlet")[
            "object"
        ]["id"]
        opening_row = next(r for r in objects["simulation_objects"] if r["descriptor"] == "Opening")
        opening = opening_row["object"]["id"]
        table = await call(
            "table",
            "nx_sim_fan_table",
            {
                "document": sid,
                "name": "Coupled public synthetic fan r1",
                "points": [[0, 1], [0.0004, 0]],
                "pressure_convention": "static",
                "rpm": 1000,
                "reference_density_kg_m3": 1.2,
                "stall_region": "Synthetic authoring only",
                "provenance_kind": "assumed",
                "provenance_source": "Coupled public binding fixture",
                "operation_id": "coupled-fan-table-r1",
            },
        )
        args = {
            "document": sid,
            "inlet": inlet,
            "field": table["field"]["id"],
            "operation_id": "coupled-fan-assign-r1",
        }
        assigned = await call("assigned", "nx_sim_assign_fan", args)
        replay = await call("assign_replay", "nx_sim_assign_fan", args)
        assert assigned["binding"] == replay["binding"] == {"mode": 5, "scale_factor": 1.0}
        assert assigned["analysis_type"] == "Coupled Thermal-Flow"
        loss_args = {
            "document": sid,
            "opening": opening,
            "coefficient": 2,
            "operation_id": "coupled-loss-r1",
        }
        if opening_row["head_loss"] is None:
            loss_args["name"] = "Coupled public opening loss r1"
        else:
            loss_args["expected_coefficient"] = opening_row["head_loss"]["coefficient"]
        loss = await call("loss", "nx_sim_head_loss", loss_args)
        loss_replay = await call("loss_replay", "nx_sim_head_loss", loss_args)
        assert loss["coefficient"] == loss_replay["coefficient"] == 2
        assert loss["analysis_type"] == "Coupled Thermal-Flow"
        await call(
            "conflict",
            "nx_sim_head_loss",
            {
                "document": sid,
                "opening": opening,
                "coefficient": 3,
                "expected_coefficient": 7,
                "operation_id": "coupled-loss-conflict-r1",
            },
            error=True,
        )
        await call(
            "wrong_kind",
            "nx_sim_assign_fan",
            {
                "document": sid,
                "inlet": inlet,
                "field": sid,
                "operation_id": "coupled-fan-wrong-kind-r1",
            },
            error=True,
        )
        before = await call(
            "before", "nx_sim_objects", {"document": sid, "include_properties": True}
        )
        await call("save", "nx_sim_save", {"document": sid, "operation_id": "coupled-fan-save-r1"})
        await call(
            "close", "nx_sim_close", {"document": sid, "operation_id": "coupled-fan-close-r1"}
        )
        await call("stale", "nx_sim_objects", {"document": sid}, error=True)
        opened = await call("reopen", "nx_sim_open", {"path": target})
        fresh = opened["document"]["id"]
        assert fresh != sid
        await call("reactivate", "nx_sim_activate", {"document": fresh})
        after = await call(
            "after", "nx_sim_objects", {"document": fresh, "include_properties": True}
        )

        def values(inventory):
            rows = inventory["simulation_objects"]
            fan = next(r for r in rows if r["descriptor"] == "Inlet")["fan_binding"]
            loss = next(r for r in rows if r["descriptor"] == "Opening")["head_loss"]
            return {
                "mode": fan["mode"],
                "scale": fan["scale_factor"],
                "field_name": fan["field"]["name"],
                "head_loss": loss,
            }

        assert values(before) == values(after)
        await call("tables_reopened", "nx_sim_fan_tables", {"document": fresh})
        # Preserve the original source document in the loaded session as well.
        await call("reopen_source", "nx_sim_open", {"path": source})
        await call("show_copy", "nx_sim_activate", {"document": fresh})
        docs = await call("documents_after", "nx_sim_documents", {"limit": 100})
        final = {d["path"]: d["modified"] for d in docs["documents"]}
        assert all(final.get(path) == flag for path, flag in initial.items())
        receipt.update(
            passed=True,
            solver_launched=False,
            exported=False,
            numerical_acceptance=False,
            committed=values(after),
            original_document_flags_preserved=True,
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
