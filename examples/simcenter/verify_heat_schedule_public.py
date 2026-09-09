"""Verify public native heat schedule lifecycle; no solve."""

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
    output = shared / "heat-schedule-public.json"

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

        tools = await client.list_tools()
        receipt["schemas"] = [
            t.model_dump(mode="json") for t in tools.tools if t.name == "nx_sim_heat_schedule"
        ]
        assert receipt["schemas"]
        fixture = await call(
            "fixture",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/T-heat-schedule-public-20260909-r1",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "operation_id": "heat-schedule-public-fixture-r1",
            },
        )
        opened = await call("open", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        document = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": document})
        await call(
            "times", "nx_sim_transient_setup", {"document": document, "output_times_s": [0, 10, 20]}
        )
        faces = await call("faces", "nx_sim_faces", {"document": document})
        body = faces["faces"][0]["body"]["id"]
        table = await call(
            "table",
            "nx_sim_scalar_table",
            {
                "document": document,
                "name": "MCP_PUBLIC_POWER",
                "axis": "time",
                "quantity": "power",
                "samples": [[0, 0], [10, 1], [20, 0]],
                "provenance": "Generic public heat schedule fixture",
            },
        )
        field = table["field"]["id"]
        base = {
            "document": document,
            "body": body,
            "field": field,
            "name": "MCP_PUBLIC_HEAT",
            "provenance": "Generic public schedule fixture",
            "scale": 2.0,
        }
        await call("negative_scale", "nx_sim_heat_schedule", {**base, "scale": -1}, error=True)
        short = await call(
            "short_table",
            "nx_sim_scalar_table",
            {
                "document": document,
                "name": "MCP_SHORT_POWER",
                "axis": "time",
                "quantity": "power",
                "samples": [[0, 0], [10, 1]],
                "provenance": "Deliberately incomplete coverage",
            },
        )
        await call(
            "coverage", "nx_sim_heat_schedule", {**base, "field": short["field"]["id"]}, error=True
        )
        args = {**base, "operation_id": "heat-schedule-public-load-r1"}
        result = await call("create", "nx_sim_heat_schedule", args)
        replay = await call("replay", "nx_sim_heat_schedule", args)
        assert result["load"]["id"] == replay["load"]["id"]
        assert result["schedule"]["samples_w"] == [[0, 0], [10, 2], [20, 0]]
        await call("duplicate", "nx_sim_heat_schedule", {**base, "name": "DUPLICATE"}, error=True)
        before = await call(
            "before",
            "nx_sim_loads",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        await call("save", "nx_sim_save", {"document": document})
        await call("close", "nx_sim_close", {"document": document})
        await call("stale", "nx_sim_scalar_tables", {"document": document}, error=True)
        opened = await call("reopen", "nx_sim_open", {"path": fixture["paths"]["sim"]})
        document = opened["document"]["id"]
        await call("reactivate", "nx_sim_activate", {"document": document})
        after = await call(
            "after",
            "nx_sim_loads",
            {"document": document, "include_properties": True, "include_targets": True},
        )
        assert before["total"] == after["total"] == 1
        old, new = before["loads"][0], after["loads"][0]
        assert old["load"]["id"] != new["load"]["id"]
        for row in [old, new]:
            prop = next(p for p in row["properties"] if p["name"] == "Heat Load")
            assert prop["field_scale"] == 2.0
            assert prop["field_definition"]["manifest"]["samples"] == [[0, 0], [10, 1], [20, 0]]
        assert old["provenance"] == new["provenance"]
        receipt.update(
            document=document,
            path=fixture["paths"]["sim"],
            passed=True,
            solver_launched=False,
            scope="Public authoring, replay, validation and reopen; field definition/scale/provenance preserved; geometric target identity audited separately",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
