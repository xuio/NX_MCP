"""Read-only job-status verification on the isolated Windows Simcenter installation."""

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
        schema = next(t for t in available.tools if t.name == "nx_sim_job_status")
        args = {
            "job_id": "isolated-flow-01",
            "job_folder": "ui-benchmarks/F-input-export-20260908-r2/jobs",
        }
        compact = await client.call_tool("nx_sim_job_status", args)
        assert not compact.isError
        assert compact.structuredContent["state"] == "solver_exited"
        assert compact.structuredContent["live_process_state"] == "not_checked"
        assert (
            "manifest" not in compact.structuredContent
            and "evidence" not in compact.structuredContent
        )
        live = await client.call_tool("nx_sim_job_status", {**args, "check_processes": True})
        assert not live.isError
        assert live.structuredContent["revision"] == compact.structuredContent["revision"]
        assert live.structuredContent["live_processes"]["state"] == "observed"
        assert len(live.structuredContent["live_processes"]["processes"]) == 2
        assert all(
            p["correlation"]["state"]
            in ("original_process_not_present", "same_process_exited", "identity_mismatch")
            for p in live.structuredContent["live_processes"]["processes"]
        )
        expanded = await client.call_tool(
            "nx_sim_job_status", {**args, "include_manifest": True, "include_evidence": True}
        )
        assert not expanded.isError
        assert (
            expanded.structuredContent["evidence"]["result"]["sha256"]
            == "6f076a9cdd65a6a25a4ebe5a3a4b97312f20041957f108adfa0edb14a46a95d8"
        )
        unknown = await client.call_tool(
            "nx_sim_job_status",
            {"job_id": "interrupted-write", "job_folder": "ui-benchmarks/F-job-ledger-20260908-r1"},
        )
        assert not unknown.isError and unknown.structuredContent["state"] == "unknown"
        assert unknown.structuredContent["launch_retry_allowed"] is False
        outside = await client.call_tool(
            "nx_sim_job_status", {"job_id": "example", "job_folder": "../outside"}
        )
        assert outside.isError
        missing = await client.call_tool(
            "nx_sim_job_status", {**args, "job_id": "nonexistent-status-test"}
        )
        assert missing.isError and missing.structuredContent["code"] == "NX_SIM_JOB_NOT_FOUND"
        result = {
            "transport": "MCP stdio -> descriptor bridge -> NX host",
            "schema": schema.model_dump(mode="json"),
            "responses": {
                name: value.model_dump(mode="json")
                for name, value in {
                    "compact": compact,
                    "live": live,
                    "expanded": expanded,
                    "unknown": unknown,
                    "outside": outside,
                    "missing": missing,
                }.items()
            },
        }
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\stdio-job-processes.json").write_text(
            json.dumps(result, indent=2)
        )
        print("MCP job status verification finished")


asyncio.run(main())
