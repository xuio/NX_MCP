"""Verify scalar tables through public MCP, replay and persistence; no solve."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "scalar-tables-native.json").read_text())
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
    output = shared / "scalar-tables-public.json"

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
        selected = {"nx_sim_scalar_table", "nx_sim_scalar_tables"}
        assert selected <= {t.name for t in tools.tools}
        receipt["schemas"] = [t.model_dump(mode="json") for t in tools.tools if t.name in selected]
        document = context["document"]
        cases = [
            {
                "name": "MCP_POWER_TIME",
                "axis": "time",
                "quantity": "power",
                "samples": [[0, 0], [10, 1], [20, 0]],
            },
            {
                "name": "MCP_TEMPERATURE_TIME",
                "axis": "time",
                "quantity": "temperature",
                "samples": [[0, 293.15], [10, 303.15], [20, 293.15]],
            },
            {
                "name": "MCP_CONDUCTIVITY_TEMPERATURE",
                "axis": "temperature",
                "quantity": "conductivity",
                "samples": [[273.15, 100], [293.15, 150], [313.15, 200]],
            },
        ]
        for options in cases:
            args = {
                **options,
                "document": document,
                "provenance": "Generic scalar table lifecycle fixture",
                "operation_id": options["name"] + "-r1",
            }
            actual = await call(options["name"], "nx_sim_scalar_table", args)
            replay = await call(options["name"] + "_replay", "nx_sim_scalar_table", args)
            assert actual["field"]["id"] == replay["field"]["id"]
            assert actual["sample_count"] == 3 and "samples" not in actual["manifest"]
            assert not actual["boundary_or_material_attached"]
        await call(
            "duplicate",
            "nx_sim_scalar_table",
            {**cases[0], "document": document, "provenance": "Duplicate test"},
            error=True,
        )
        await call(
            "invalid_samples",
            "nx_sim_scalar_table",
            {
                **cases[0],
                "name": "INVALID",
                "samples": [[0, 1], [0, 2]],
                "document": document,
                "provenance": "Invalid test",
            },
            error=True,
        )
        page = await call(
            "compact_page", "nx_sim_scalar_tables", {"document": document, "limit": 2}
        )
        assert page["total"] == 3 and page["next_offset"] == 2
        assert all(
            "samples" not in t["manifest"] and "samples_si" not in t["readback"]
            for t in page["tables"]
        )
        last = await call(
            "last_page", "nx_sim_scalar_tables", {"document": document, "offset": 2, "limit": 2}
        )
        assert len(last["tables"]) == 1 and last["next_offset"] is None
        before = await call(
            "before", "nx_sim_scalar_tables", {"document": document, "include_samples": True}
        )
        assert before["total"] == 3
        for table in before["tables"]:
            expected = next(c for c in cases if c["name"] == table["manifest"]["name"])
            assert table["readback"]["samples_si"] == expected["samples"]
        await call("save", "nx_sim_save", {"document": document})
        await call("close", "nx_sim_close", {"document": document})
        await call("stale", "nx_sim_scalar_tables", {"document": document}, error=True)
        reopened = await call("reopen", "nx_sim_open", {"path": context["path"]})
        document = reopened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": document})
        after = await call(
            "after", "nx_sim_scalar_tables", {"document": document, "include_samples": True}
        )
        assert after["total"] == before["total"]
        for old, new in zip(before["tables"], after["tables"], strict=True):
            assert old["field"]["id"] != new["field"]["id"]
            for key in ["manifest", "manifest_sha256", "readback"]:
                assert old[key] == new[key], key
        receipt.update(
            passed=True,
            document=document,
            path=context["path"],
            solver_launched=False,
            scope="Native/public table authoring, replay, paging and persistence; load/material binding and numerical behavior not established",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
