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
        compact = await client.call_tool("nx_sim_job_status", {"job_id": "fine-k0-flow-01"})
        expanded = await client.call_tool(
            "nx_sim_job_status", {"job_id": "fine-k0-flow-01", "include_launch_gate": True}
        )
        assert not compact.isError and not expanded.isError
        assert "launch_gate" not in compact.structuredContent
        gate = expanded.structuredContent["launch_gate"]
        assert gate["state"] == "unclaimed"
        assert gate["solver_process_state"] == "not_checked"
        assert not gate["launch_authorized_by_inspection"]
        after = await client.call_tool("nx_sim_documents", {"limit": 100})
        assert not after.isError
        assert {d["path"]: d["modified"] for d in docs.structuredContent["documents"]} == {
            d["path"]: d["modified"] for d in after.structuredContent["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-gate-inspection.json").write_text(
            json.dumps(
                {
                    "compact": compact.model_dump(mode="json"),
                    "expanded": expanded.model_dump(mode="json"),
                    "modified_flags_preserved": True,
                },
                indent=2,
            )
        )
        print("Native public optional launch-gate inspection verified")


asyncio.run(main())
