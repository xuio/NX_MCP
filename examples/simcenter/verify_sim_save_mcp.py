"""Conduction setup through public MCP tools on the isolated Windows Simcenter installation."""

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
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-sim-save.json")
        responses = {}

        async def call(name, args, key):
            result = await client.call_tool(name, args)
            responses[key] = result.model_dump(mode="json")
            output.write_text(
                json.dumps(
                    {"transport": "real MCP to Simcenter UI", "responses": responses}, indent=2
                )
            )
            assert not result.isError, result.structuredContent
            return result.structuredContent

        docs = await call("nx_sim_documents", {"limit": 100}, "before")
        sim = next(d for d in docs["documents"] if d["work"] and d["document_type"] == "SimPart")
        assert sim["path"].endswith(r"A-temperature-mcp-20260908-r1\saved_temperature.sim"), sim
        simid = sim["document"]["id"]
        deps = await call("nx_sim_dependencies", {"document": simid}, "dependencies")
        fempath = next(d["path"] for d in deps["documents"] if d["document_type"] == "FemPart")
        fem = next(d for d in docs["documents"] if d["path"] == fempath)
        for label, doc in (("fem", fem), ("sim", sim)):
            args = {
                "document": doc["document"]["id"],
                "operation_id": "conduction-save-" + label + "-01",
            }
            saved = await call("nx_sim_save", args, label)
            assert saved["saved"] and saved["other_modified_flags_unchanged"]
            replay = await call("nx_sim_save", args, label + "_replay")
            assert replay["backup_path"] == saved["backup_path"]
            import hashlib

            assert (
                hashlib.sha256(Path(saved["backup_path"]).read_bytes()).hexdigest()
                == saved["previous_file"]["sha256"]
            )
        after = await call("nx_sim_documents", {"limit": 100}, "after")
        for doc in after["documents"]:
            if doc["path"] in (sim["path"], fem["path"]):
                assert not doc["modified"], doc
        print("Native public FEM/SIM save, backups, and replay verified")


asyncio.run(main())
