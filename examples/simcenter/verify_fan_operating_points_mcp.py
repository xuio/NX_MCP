"""Read-only MCP verification on the isolated Windows Simcenter installation."""

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
        available = await client.list_tools()
        assert any(t.name == "nx_sim_solutions" for t in available.tools)
        docs = await client.call_tool("nx_sim_documents", {"offset": 0, "limit": 100})
        if docs.isError:
            raise RuntimeError(docs.structuredContent)
        document = next(
            d
            for d in docs.structuredContent["documents"]
            if d["work"] and d["document_type"] == "SimPart"
        )["document"]["id"]
        results = {}
        for job, log_name, flow, pressure in [
            ("fine-k0-flow-01", "fine_k0_solve_r1-Flow_benchmark.log", 0.0002524, 0.3691),
            ("auto-observed-flow-01", "auto_flow_r1-Flow_benchmark.log", 0.0001912, 0.5221),
        ]:
            result = await client.call_tool(
                "nx_sim_flow_log", {"job_id": job, "log_name": log_name, "limit": 1}
            )
            results[job] = result.model_dump(mode="json")
            assert not result.isError, result.structuredContent
            summary = result.structuredContent["fan_operating_points"]
            assert summary["state"] == "reported" and len(summary["fans"]) == 1
            fan = summary["fans"][0]
            assert abs(fan["volume_flow_m3_s"] - flow) < 1e-12
            assert abs(fan["pressure_rise_Pa"] - pressure) < 1e-9
            assert fan["pressure_convention"] == "unverified"
            assert result.structuredContent["numerical_convergence"] == "not_established"
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        results["document_flags_preserved"] = True
        Path(
            r"Z:\nx-mcp-integration\simcenter-discovery\stdio-fan-operating-points.json"
        ).write_text(json.dumps(results, indent=2))
        print("Native public fan operating points verified for both matched duct jobs")


asyncio.run(main())
