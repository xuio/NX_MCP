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

        async def call(name, args):
            response = await client.call_tool(name, args)
            if response.isError:
                raise RuntimeError(response.model_dump(mode="json"))
            return response.structuredContent

        docs = await call("nx_sim_documents", {"limit": 100})
        args = {
            "job_id": "isolated-flow-01",
            "job_folder": "ui-benchmarks/F-input-export-20260908-r2/jobs",
            "log_name": "flow_input_r2-Flow_benchmark.log",
            "maximum_bytes": 1024,
        }
        before = await call(
            "nx_sim_job_status", {"job_id": args["job_id"], "job_folder": args["job_folder"]}
        )
        assert "process_binding_evidence" not in before
        catalog = await call(
            "nx_sim_job_logs",
            {"job_id": args["job_id"], "job_folder": args["job_folder"], "limit": 100},
        )
        listed = next(row for row in catalog["logs"] if row["log_name"] == args["log_name"])
        args["file_identity"] = listed["file_identity"]
        first = await call("nx_sim_job_log", args)
        second = await call(
            "nx_sim_job_log",
            {**args, "offset": first["next_offset"], "file_identity": first["file_identity"]},
        )
        assert first["next_offset"] == second["offset"] and second["next_offset"] > second["offset"]
        assert first["request_sha256"] == before["request_sha256"]
        bad = await client.call_tool("nx_sim_job_log", {**args, "log_name": "../outside.log"})
        assert bad.isError
        replaced = await client.call_tool("nx_sim_job_log", {**args, "file_identity": "different"})
        assert replaced.isError
        after = await call(
            "nx_sim_job_status", {"job_id": args["job_id"], "job_folder": args["job_folder"]}
        )
        # Every MCP call has its own operation receipt; compare persisted job state.
        stable = (
            "job_id",
            "state",
            "revision",
            "request_sha256",
            "observed_at",
            "launch_retry_allowed",
            "process_binding_revision",
        )
        assert {k: before[k] for k in stable} == {k: after[k] for k in stable}
        final_docs = await call("nx_sim_documents", {"limit": 100})
        assert {d["path"]: d["modified"] for d in docs["documents"]} == {
            d["path"]: d["modified"] for d in final_docs["documents"]
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-job-log.json").write_text(
            json.dumps(
                {
                    "catalog": catalog,
                    "first": first,
                    "second": second,
                    "path_rejection": bad.model_dump(mode="json"),
                    "identity_rejection": replaced.model_dump(mode="json"),
                    "job_unchanged": True,
                    "document_flags_preserved": True,
                },
                indent=2,
            )
        )
        print("Public native job-log paging and ownership/cursor guards verified")


asyncio.run(main())
