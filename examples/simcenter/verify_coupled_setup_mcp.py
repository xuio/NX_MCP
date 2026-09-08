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
        responses = {}

        async def call(key, method, args):
            result = await client.call_tool(method, args)
            responses[key] = result.model_dump(mode="json")
            (stage / "stdio-coupled-setup.json").write_text(
                json.dumps(
                    {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": responses},
                    indent=2,
                )
            )
            return result

        created = await call(
            "created",
            "nx_sim_create_benchmark",
            {
                "folder": "ui-benchmarks/E-coupled-mcp-20260908-r1",
                "analysis_type": "coupled_thermal_flow",
                "operation_id": "coupled-mcp-create-r1",
            },
        )
        assert not created.isError, created.structuredContent
        docs = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        sim = next(d for d in docs if d["work"] and d["document_type"] == "SimPart")
        document = sim["document"]["id"]
        step = await call(
            "step",
            "nx_sim_flow_setup",
            {
                "document": document,
                "action": "create_step",
                "name": "Coupled acceptance setup",
                "operation_id": "coupled-mcp-step-r1",
            },
        )
        assert not step.isError and step.structuredContent["descriptor"] == "Step - Thermal Flow", (
            step.structuredContent
        )
        args = {
            "document": document,
            "action": "attach_defaults",
            "name": "Coupled defaults",
            "operation_id": "coupled-mcp-tables-r1",
        }
        tables = await call("tables", "nx_sim_flow_setup", args)
        assert not tables.isError, tables.structuredContent
        assert (
            len(tables.structuredContent["tables"]) == 4
            and not tables.structuredContent["solve_ready"]
        )
        assert tables.structuredContent["unresolved_controls"] == [
            "Coupled Solution Parameters descriptor mapping"
        ]
        replay = await call("replay", "nx_sim_flow_setup", args)
        assert (
            not replay.isError
            and replay.structuredContent["tables"] == tables.structuredContent["tables"]
        )
        conflict = await call(
            "conflict", "nx_sim_flow_setup", {**args, "operation_id": "coupled-mcp-conflict-r1"}
        )
        assert conflict.isError and conflict.structuredContent["code"] == "NX_SIM_TABLE_EXISTS", (
            conflict.structuredContent
        )
        saved = await call(
            "saved", "nx_sim_save", {"document": document, "operation_id": "coupled-mcp-save-r1"}
        )
        assert not saved.isError, saved.structuredContent
        print(
            "Native coupled step, four tables, retry, existing-table rejection and save passed; coupled controls remain unresolved"
        )


asyncio.run(main())
