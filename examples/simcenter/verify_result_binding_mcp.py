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
        mismatch = await client.call_tool(
            "nx_sim_result_identity", {"document": document, "job_id": "fine-k0-flow-01"}
        )
        results["wrong_owner"] = mismatch.model_dump(mode="json")
        assert mismatch.isError, mismatch.structuredContent
        assert "NX_SIM_RESULT_JOB_MISMATCH" in json.dumps(mismatch.structuredContent)
        opened = await client.call_tool(
            "nx_sim_open",
            {
                "path": "ui-benchmarks/D-fine-k0-solve-20260908-r1/fine_k0_solve_r1.sim",
                "operation_id": "result-binding-open-r1",
            },
        )
        results["opened"] = opened.model_dump(mode="json")
        assert not opened.isError
        result = await client.call_tool(
            "nx_sim_result_identity",
            {"document": opened.structuredContent["document"]["id"], "job_id": "fine-k0-flow-01"},
        )
        results["bound_result"] = result.model_dump(mode="json")
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-result-binding.json").write_text(
            json.dumps(results, indent=2)
        )
        assert not result.isError, result.structuredContent
        assert result.structuredContent["job_binding"][
            "associated_result_matches_observed_artifact"
        ]
        assert result.structuredContent["job_binding"]["model_result_freshness"] == "not_verified"
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        results["document_flags_preserved"] = True
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-result-binding.json").write_text(
            json.dumps(results, indent=2)
        )
        print(
            "Native result owner rejection and recorded artifact binding verified; revision status remains explicit"
        )


asyncio.run(main())
