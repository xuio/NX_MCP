"""Prepare a fresh native flow input/job through public MCP; no solver launch."""

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
        schema = next(t for t in available.tools if t.name == "nx_sim_prepare_solve")
        docs = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        row = next(d for d in docs if d["work"] and d["document_type"] == "SimPart")
        assert row["path"].endswith("F-input-export-20260908-r2\\flow_input_r2.sim")
        before = {d["path"]: d["modified"] for d in docs if d != row}
        copied = await client.call_tool(
            "nx_sim_save_as",
            {
                "document": row["document"]["id"],
                "path": "ui-benchmarks/F-prepare-20260908-r1/prepared_flow_r1.sim",
                "operation_id": "prepare-flow-copy-r1",
            },
        )
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-preparation.json")
        responses = {"copied": copied.model_dump(mode="json")}

        def record():
            output.write_text(
                json.dumps(
                    {
                        "transport": "real MCP stdio -> Simcenter UI bridge",
                        "schema": schema.model_dump(mode="json"),
                        "responses": responses,
                    },
                    indent=2,
                )
            )

        record()
        assert not copied.isError, copied.structuredContent
        args = {
            "document": copied.structuredContent["document"]["id"],
            "job_id": "public-prepared-flow-01",
            "job_folder": "simcenter-jobs",
            "operation_id": "prepare-flow-r1",
        }
        prepared = await client.call_tool("nx_sim_prepare_solve", args)
        responses["prepared"] = prepared.model_dump(mode="json")
        record()
        assert not prepared.isError, prepared.structuredContent
        result = prepared.structuredContent
        assert result["state"] == "accepted" and not result["solver_launched_by_call"]
        assert result["mesh_counts"]["elements"] == 186765
        replay = await client.call_tool(
            "nx_sim_prepare_solve", {**args, "operation_id": "prepare-flow-r1-readback"}
        )
        responses["replay"] = replay.model_dump(mode="json")
        record()
        assert not replay.isError and replay.structuredContent["replayed"]
        assert replay.structuredContent["request_sha256"] == result["request_sha256"]
        status = await client.call_tool(
            "nx_sim_job_status", {"job_id": args["job_id"], "include_manifest": True}
        )
        responses["job"] = status.model_dump(mode="json")
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        responses["unrelated_flags_preserved"] = all(
            next(d for d in after if d["path"] == path)["modified"] == flag
            for path, flag in before.items()
        )
        record()
        assert not status.isError and status.structuredContent["state"] == "accepted"
        assert responses["unrelated_flags_preserved"]
        print(
            "Native public preparation/export, durable replay and model preservation passed; no solve launched"
        )


asyncio.run(main())
