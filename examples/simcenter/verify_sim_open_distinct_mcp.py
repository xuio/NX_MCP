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
        import shutil

        stage = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
        workspace = Path(r"D:\CAD\SIMCENTER_MCP_WORKSPACE")
        folder = workspace / "ui-benchmarks/scenario-multi-mcp-20260908-r1"
        sim_path, fem_path = folder / "public_open_r1.sim", folder / "public_open_r1.fem"
        assert sim_path.is_file() and fem_path.is_file()
        distinct_fem = folder / "public_open_fem_r2.fem"
        if distinct_fem.exists():
            raise ValueError("Fresh distinct FEM name required")
        shutil.copy2(fem_path, distinct_fem)
        fem_path = distinct_fem
        output = stage / "stdio-sim-open-distinct.json"
        responses = {}

        async def call(key, args):
            result = await client.call_tool("nx_sim_open", args)
            responses[key] = result.model_dump(mode="json")
            output.write_text(
                json.dumps(
                    {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": responses},
                    indent=2,
                )
            )
            return result

        before = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        flags = {d["path"]: d["modified"] for d in before}
        first = await call(
            "fresh_sim", {"path": str(sim_path), "operation_id": "sim-open-loaded-r2"}
        )
        assert not first.isError and first.structuredContent["already_loaded"], (
            first.structuredContent
        )
        reused = await call(
            "reuse_sim",
            {"path": str(sim_path.relative_to(workspace)), "operation_id": "sim-open-reuse-r2"},
        )
        assert not reused.isError and reused.structuredContent["already_loaded"], (
            reused.structuredContent
        )
        assert (
            first.structuredContent["document"]["id"] == reused.structuredContent["document"]["id"]
        )
        assert first.structuredContent["modified"] == reused.structuredContent["modified"]
        fem = await call("fresh_fem", {"path": str(fem_path), "operation_id": "fem-open-fresh-r2"})
        assert not fem.isError and not fem.structuredContent["already_loaded"], (
            fem.structuredContent
        )
        back = await call(
            "return_sim", {"path": str(sim_path), "operation_id": "sim-open-return-r2"}
        )
        assert not back.isError and back.structuredContent["already_loaded"], back.structuredContent
        missing = await call(
            "missing", {"path": str(folder / "missing.sim"), "operation_id": "sim-open-missing-r2"}
        )
        assert missing.isError and missing.structuredContent["code"] == "NX_NOT_FOUND"
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        assert {d["path"]: d["modified"] for d in after if d["path"] in flags} == flags
        responses["other_document_flags_preserved"] = True
        output.write_text(
            json.dumps(
                {"transport": "real MCP stdio -> Simcenter UI bridge", "responses": responses},
                indent=2,
            )
        )
        print(
            "Native MCP fresh FEM/SIM open, loaded reuse, switching and missing-path rejection passed"
        )


asyncio.run(main())
