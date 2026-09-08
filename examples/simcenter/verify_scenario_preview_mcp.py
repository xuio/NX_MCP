"""Verify read-only scenario import against real SIM/FEM objects through MCP."""

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
        stage = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
        receipt = json.loads((stage / "assignment-builders.json").read_text())
        assert receipt["status"] == "success", receipt
        args = receipt["args"]
        tools = await client.list_tools()
        assert any(t.name == "nx_sim_scenario_preview" for t in tools.tools)
        before = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        good = await client.call_tool("nx_sim_scenario_preview", args)
        assert not good.isError, good.structuredContent
        assert good.structuredContent["totals_W"]["internal_heat"] == 8
        assert good.structuredContent["totals_W"]["exported_electrical"] == 10
        bad = await client.call_tool("nx_sim_scenario_preview", {**args, "region_targets": {}})
        assert bad.isError, bad.structuredContent
        stale = await client.call_tool(
            "nx_sim_scenario_preview", {**args, "region_targets": {"SOC": "obj_stale"}}
        )
        assert stale.isError, stale.structuredContent
        outside = await client.call_tool(
            "nx_sim_scenario_preview", {**args, "path": "../outside.csv"}
        )
        assert outside.isError, outside.structuredContent
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        assert before == after
        (stage / "stdio-scenario-preview.json").write_text(
            json.dumps(
                {
                    "transport": "real MCP stdio -> Simcenter UI bridge",
                    "success": good.model_dump(mode="json"),
                    "missing_mapping": bad.model_dump(mode="json"),
                    "stale_target": stale.model_dump(mode="json"),
                    "outside_workspace": outside.model_dump(mode="json"),
                    "document_state_preserved": True,
                },
                indent=2,
            )
        )
        print("Native MCP scenario preview and invalid-selection rejection passed")


asyncio.run(main())
