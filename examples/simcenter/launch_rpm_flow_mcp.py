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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-rpm-flow-launch.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        source = next(
            d
            for d in docs.structuredContent["documents"]
            if d["path"].endswith("refined_flow_r1.sim")
        )
        activated = await call(
            "activate",
            "nx_sim_activate",
            {"document": source["document"]["id"], "operation_id": "rpm-flow-activate-r1"},
        )
        assert not activated.isError
        copied = await call(
            "copy",
            "nx_sim_save_as",
            {
                "document": source["document"]["id"],
                "path": "ui-benchmarks/rpm-flow-solve-20260908-r1/rpm_flow_r1.sim",
                "operation_id": "rpm-flow-copy-r1",
            },
        )
        assert not copied.isError, copied.structuredContent
        document = copied.structuredContent["document"]["id"]
        objects = await call("objects", "nx_sim_objects", {"document": document, "limit": 100})
        inlet = next(
            r
            for r in objects.structuredContent["simulation_objects"]
            if r["object"]["name"] == "Duct Inlet"
        )
        tables = await call(
            "tables",
            "nx_sim_fan_tables",
            {"document": document, "include_samples": True, "limit": 100},
        )
        source_curve = next(
            r["manifest"]
            for r in tables.structuredContent["tables"]
            if r["field"]["id"] == inlet["fan_binding"]["field"]["id"]
        )
        assert source_curve["rpm"] == 1000 and source_curve["pressure_convention"] == "static"
        base = await call(
            "base_curve",
            "nx_sim_fan_table",
            {
                "document": document,
                "name": "RPM study source",
                "points": [[p["flow_m3_s"], p["pressure_Pa"]] for p in source_curve["points"]],
                "pressure_convention": "static",
                "rpm": 1000,
                "reference_density_kg_m3": source_curve["reference_density_kg_m3"],
                "stall_region": source_curve["stall_region"],
                "provenance_kind": "assumed",
                "provenance_source": "Synthetic duct RPM sensitivity benchmark",
                "scaling_rpm_range": [900, 1100],
                "scaling_validity": "Synthetic same-geometry fan-law sensitivity; not supplier validated",
                "operation_id": "rpm-flow-source-r1",
            },
        )
        assert not base.isError, base.structuredContent
        scaled = await call(
            "scaled_curve",
            "nx_sim_scale_fan_table",
            {
                "document": document,
                "source_field": base.structuredContent["field"]["id"],
                "name": "RPM study 1100",
                "rpm": 1100,
                "operation_id": "rpm-flow-scale-r1",
            },
        )
        assert not scaled.isError, scaled.structuredContent
        assigned = await call(
            "assignment",
            "nx_sim_assign_fan",
            {
                "document": document,
                "inlet": inlet["object"]["id"],
                "field": scaled.structuredContent["field"]["id"],
                "operation_id": "rpm-flow-assign-r1",
            },
        )
        assert not assigned.isError, assigned.structuredContent
        saved = await call(
            "save", "nx_sim_save", {"document": document, "operation_id": "rpm-flow-save-r1"}
        )
        assert not saved.isError, saved.structuredContent
        args = {"document": document, "job_id": "rpm-flow-1100-r1"}
        prepared = await call(
            "prepare", "nx_sim_prepare_solve", {**args, "operation_id": "rpm-flow-prepare-r1"}
        )
        assert not prepared.isError, prepared.structuredContent
        launched = await call(
            "launch", "nx_sim_launch", {**args, "operation_id": "rpm-flow-launch-r1"}
        )
        assert not launched.isError, launched.structuredContent
        print("1100 RPM duct job launched; observe existing job rpm-flow-1100-r1")


asyncio.run(main())
