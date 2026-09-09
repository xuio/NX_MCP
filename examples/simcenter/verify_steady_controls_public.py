"""Verify contact authoring through the public MCP using an isolated fixture."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    context = json.loads((shared / "steady-controls-native.json").read_text())
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
    receipt = {"responses": {}}
    output = shared / "steady-controls-public-launch.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][label] = response.model_dump(mode="json")
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        tools = await client.list_tools()
        assert any(t.name == "nx_sim_steady_thermal_controls" for t in tools.tools)
        args = {
            "document": context["document"],
            "maximum_temperature_change_k": 0.001,
            "iteration_limit": 100,
            "relative_heat_balance": None,
            "operation_id": "steady-controls-explicit-r1",
        }
        await call(
            "invalid",
            "nx_sim_steady_thermal_controls",
            {**args, "relative_heat_balance": 1.5, "operation_id": "steady-controls-invalid-r1"},
            error=True,
        )
        actual = await call("configure", "nx_sim_steady_thermal_controls", args)
        replay = await call("replay", "nx_sim_steady_thermal_controls", args)
        assert actual["parameter_table"]["id"] == replay["parameter_table"]["id"]
        assert (
            actual["actual"]["mode"] == 1 and not actual["actual"]["relative_heat_balance_enabled"]
        )
        await call(
            "save",
            "nx_sim_save",
            {"document": context["document"], "operation_id": "steady-controls-save-r1"},
        )
        job = await call(
            "prepare",
            "nx_sim_prepare_solve",
            {
                "document": context["document"],
                "job_id": "contact-explicit-r1",
                "operation_id": "contact-explicit-prepare-r1",
            },
        )
        import xml.etree.ElementTree as ET

        root = ET.parse(job["input_path"]).getroot()
        table = root.find(".//ThermalParameters")

        def value(name):
            rows = [p for p in table.findall("Property") if p.get("name") == name]
            assert len(rows) == 1
            return float(rows[0].findtext("Value"))

        assert value("Steady State - Convergence Criteria") == 1
        assert value("Steady State - Maximum Temperature Change") == 0.001
        assert value("Steady State - Heat Imbalance") == 0
        assert value("Thermal Steady State - Iteration Limit") == 100
        assert job["mesh_counts"]["elements"] == 200
        receipt["export_controls_verified"] = True
        record()
        # A separate permanent job identity and unchanged physical benchmark assumptions.
        criteria = json.loads((shared / "contact-acceptance.json").read_text())
        criteria.update(
            job_id="contact-explicit-r1",
            input_sha256_before_launch=job["input_sha256"],
            native_controls={
                "mode": "specified",
                "maximum_temperature_change_k": 0.001,
                "relative_heat_balance": None,
                "iteration_limit": 100,
            },
        )
        criterion_path = shared / "contact-explicit-acceptance.json"
        if criterion_path.exists():
            assert json.loads(criterion_path.read_text()) == criteria
        else:
            criterion_path.write_text(json.dumps(criteria, indent=2))
        await call(
            "launch",
            "nx_sim_launch",
            {
                "document": context["document"],
                "job_id": "contact-explicit-r1",
                "operation_id": "contact-explicit-launch-r1",
            },
        )
        receipt.update(
            passed=True,
            document=context["document"],
            path=context["path"],
            scope="Public explicit-controls discovery/replay/export and native launch; numerical acceptance separate",
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
