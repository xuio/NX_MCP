"""Verify public native group summaries and invalid selection handling; no solve."""

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
    output = shared / "temperature-regions-public.json"

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

        opened = await call(
            "open",
            "nx_sim_open",
            {"path": "ui-benchmarks/B-contact-explicit-20260909-r1/contact_explicit_r1.sim"},
        )
        sid = opened["document"]["id"]
        await call("activate", "nx_sim_activate", {"document": sid})
        identity = await call("identity", "nx_sim_result_identity", {"document": sid})
        digest = identity["files"][0]["sha256"]
        args = {"document": sid, "result_sha256": digest}
        first = await call("first", "nx_sim_temperature_regions", {**args, "limit": 1})
        second = await call(
            "second", "nx_sim_temperature_regions", {**args, "limit": 1, "offset": 1}
        )
        empty = await call("empty", "nx_sim_temperature_regions", {**args, "offset": 2})
        assert first["next_offset"] == 1 and second["next_offset"] is None and empty["items"] == []
        rows = first["items"] + second["items"]
        assert all(r["node_count"] == 45 and r["element_count"] == 100 for r in rows)
        expected = {
            0.0: (20.99782371520996, 21.25148582458496, 21.14748691982693),
            10.0: (20.0, 20.50029754638672, 20.249729114108614),
        }
        for row in rows:
            lo, hi, mean = expected[row["bounds"]["minimum"][0]]
            assert row["minimum"]["temperature"] == lo and row["maximum"]["temperature"] == hi
            assert abs(row["arithmetic_nodal_mean"] - mean) < 1e-10
        surface = await call("surface", "nx_sim_temperature_regions", {**args, "dimension": "2d"})
        assert (
            surface["items"][0]["element_count"] == 42 and surface["items"][0]["node_count"] == 36
        )
        wrong = await call(
            "wrong_revision",
            "nx_sim_temperature_regions",
            {**args, "result_sha256": "0" * 64},
            error=True,
        )
        assert wrong["code"] == "NX_SIM_RESULT_CHANGED"
        budget = await call(
            "budget", "nx_sim_temperature_regions", {**args, "maximum_entities": 1}, error=True
        )
        assert budget["code"] == "NX_SIM_INSPECTION_LIMIT"
        after = await call("identity_after", "nx_sim_result_identity", {"document": sid})
        assert after["files"] == identity["files"]
        await call(
            "show",
            "nx_sim_show_temperature",
            {"document": sid, "operation_id": "temperature-regions-contact-show-r1"},
        )
        receipt.update(passed=True, solver_launched=False, groups=rows)
        record()


if __name__ == "__main__":
    asyncio.run(main())
