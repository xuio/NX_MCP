"""Inspect the completed native flow job through the read-only public log audit."""

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
        schema = next(t for t in available.tools if t.name == "nx_sim_flow_log")
        args = {
            "job_id": "public-prepared-flow-01",
            "log_name": "prepared_flow_r1-Flow_benchmark.log",
            "limit": 30,
        }
        before = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        first = await client.call_tool("nx_sim_flow_log", args)
        output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-flow-audit.json")
        responses = {"first": first.model_dump(mode="json")}

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
        assert not first.isError, first.structuredContent
        r = first.structuredContent
        assert r["history_total"] == 60 and r["next_offset"] == 30
        assert r["last_iteration"] == 15 and r["final_residual_criteria_met"]
        assert r["reported_imbalances"]["mass"]["value"] == 0.008865
        assert r["numerical_convergence"] == "not_established"
        second = await client.call_tool("nx_sim_flow_log", {**args, "offset": 30})
        rejected = await client.call_tool("nx_sim_flow_log", {**args, "log_name": "../outside.log"})
        after = (await client.call_tool("nx_sim_documents", {"limit": 100})).structuredContent[
            "documents"
        ]
        responses.update(
            second=second.model_dump(mode="json"),
            rejected=rejected.model_dump(mode="json"),
            document_flags_preserved={
                d["path"]: (d["modified"], d["work"], d["display"]) for d in before
            }
            == {d["path"]: (d["modified"], d["work"], d["display"]) for d in after},
        )
        record()
        assert not second.isError and second.structuredContent["next_offset"] is None
        assert second.structuredContent["log_sha256"] == r["log_sha256"]
        assert rejected.isError and responses["document_flags_preserved"]
        print(
            "Native job flow audit, paging and traversal rejection passed; numerical acceptance remains separate"
        )


asyncio.run(main())
