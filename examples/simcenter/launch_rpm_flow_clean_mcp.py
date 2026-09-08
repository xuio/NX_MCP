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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-rpm-flow-clean-launch.json")

        async def call(label, tool, arguments):
            result = await client.call_tool(tool, arguments)
            responses[label] = result.model_dump(mode="json")
            output.write_text(json.dumps({"responses": responses}, indent=2))
            return result

        docs = await call("documents", "nx_sim_documents", {"limit": 100})
        source = next(
            d for d in docs.structuredContent["documents"] if d["path"].endswith("rpm_flow_r1.sim")
        )
        assert not source["modified"]
        document = source["document"]["id"]
        copied = await call(
            "copy_clean",
            "nx_sim_save_as",
            {
                "document": document,
                "path": "ui-benchmarks/rpm-flow-clean-20260908-r1/rpm_flow_1100_r1.sim",
                "operation_id": "rpm-flow-clean-copy-r1",
            },
        )
        assert not copied.isError, copied.structuredContent
        document = copied.structuredContent["document"]["id"]
        saved = await call(
            "save_clean",
            "nx_sim_save",
            {"document": document, "operation_id": "rpm-flow-clean-save-r1"},
        )
        assert not saved.isError, saved.structuredContent
        assert "simcenter-save-backups" in saved.structuredContent["backup_path"]
        args = {"document": document, "job_id": "rpm-flow-1100-r1"}
        prepared = await call(
            "prepare", "nx_sim_prepare_solve", {**args, "operation_id": "rpm-flow-clean-prepare-r1"}
        )
        assert not prepared.isError, prepared.structuredContent
        launched = await call(
            "launch", "nx_sim_launch", {**args, "operation_id": "rpm-flow-clean-launch-r1"}
        )
        assert not launched.isError, launched.structuredContent
        print("1100 RPM duct job launched from clean output directory; observe rpm-flow-1100-r1")


asyncio.run(main())
