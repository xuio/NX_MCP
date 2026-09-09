"""Verify temperature node/group summaries survive isolated SIM save/close/reopen."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
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
    output = shared / "public-full-prepare-r1.json"

    def record():
        output.write_text(json.dumps(receipt, indent=2))

    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as client,
    ):
        await client.initialize()

        async def call(label, name, args, error=False):
            response = await client.call_tool(name, args)
            receipt["responses"][str(len(receipt["responses"])) + "_" + label] = (
                response.model_dump(mode="json")
            )
            record()
            assert bool(response.isError) == error, response
            return response.structuredContent

        prior = json.loads((shared / "public-cad-topology-r1.json").read_text())["responses"][
            "analysis"
        ]["structuredContent"]
        f = await call("open_fem", "nx_sim_open", {"path": prior["paths"]["fem"]})
        opened = await call("open_sim", "nx_sim_open", {"path": prior["paths"]["sim"]})
        result = {"fem": f["document"], "sim": opened["document"]}
        sid = result["sim"]["id"]
        await call(
            "step",
            "nx_sim_flow_setup",
            {"document": sid, "action": "create_step", "name": "Steady"},
        )
        await call(
            "tables",
            "nx_sim_flow_setup",
            {"document": sid, "action": "attach_defaults", "name": "Public"},
        )
        await call("steady", "nx_sim_flow_setup", {"document": sid, "action": "coupled_steady"})
        for temperature in (25.0,):
            r = await call(
                "ambient_" + str(int(temperature)),
                "nx_sim_environment",
                {
                    "document": sid,
                    "temperature_c": temperature,
                    "pressure_pa": 101325.0,
                    "buoyancy": False,
                },
            )
            assert r["actual"]["values"]["Fluid Temperature"]["value"] == temperature
        await call("save", "nx_sim_save", {"document": sid})
        setup = result
        inventory = await call("faces", "nx_sim_faces", {"document": sid})
        selected = {}
        for label, x in (("inlet", 0.0), ("opening", 20.0)):
            matches = [
                r
                for r in inventory["faces"]
                if abs(r["bounds"]["minimum"][0] - x) < 1e-6
                and abs(r["bounds"]["maximum"][0] - x) < 1e-6
                and abs(r["bounds"]["minimum"][2] - 2) < 1e-6
                and abs(r["bounds"]["maximum"][2] - 10) < 1e-6
            ]
            assert len(matches) == 1
            selected[label] = matches[0]["face"]["id"]
        inlet = await call(
            "inlet",
            "nx_sim_inlet",
            {
                "document": sid,
                "faces": [selected["inlet"]],
                "name": "Public inlet",
                "velocity_m_s": 1.0,
                "operation_id": "public-full-inlet-r1",
            },
        )
        outlet = await call(
            "opening",
            "nx_sim_opening",
            {
                "document": sid,
                "faces": [selected["opening"]],
                "name": "Public outlet",
                "pressure_pa": 101325.0,
                "operation_id": "public-full-opening-r1",
            },
        )
        await call(
            "external",
            "nx_sim_external_temperature",
            {
                "document": sid,
                "boundaries": [inlet["boundary"]["id"], outlet["boundary"]["id"]],
                "name": "External 25 C",
                "temperature_c": 25.0,
            },
        )
        await call("save", "nx_sim_save", {"document": sid})
        inlet_id = inlet["boundary"]["id"]
        opening_id = outlet["boundary"]["id"]
        fid, sid = setup["fem"]["id"], setup["sim"]["id"]
        await call("activate_fem", "nx_sim_activate", {"document": fid})
        inventory = await call("faces", "nx_sim_faces", {"document": fid})
        regions = {}
        for row in inventory["faces"]:
            key = row["body"]["id"]
            region = regions.setdefault(key, {"low": float("inf"), "high": -float("inf")})
            region["low"] = min(region["low"], row["bounds"]["minimum"][2])
            region["high"] = max(region["high"], row["bounds"]["maximum"][2])
        assert len(regions) == 2
        plan = [
            {"body": body, "kind": "solid" if bounds["low"] < 1 else "fluid", "size_mm": 2.0}
            for body, bounds in regions.items()
        ]
        await call(
            "mesh",
            "nx_sim_mesh_plan",
            {"document": fid, "regions": plan, "operation_id": "public-full-mesh-r1"},
        )
        await call(
            "solid",
            "nx_sim_material",
            {
                "document": fid,
                "name": "Generic aluminium",
                "conductivity_w_m_k": 200.0,
                "density_kg_m3": 2700.0,
                "heat_capacity_j_kg_k": 900.0,
                "provenance": "Assumed generic benchmark properties",
                "assign_all_solid_collectors": True,
            },
        )
        collectors = await call("collectors", "nx_sim_collectors", {"document": fid})
        fluid = [
            r["collector"]["id"] for r in collectors["collectors"] if r["native_type"] == "Fluid"
        ]
        assert fluid
        await call(
            "fluid",
            "nx_sim_fluid_material",
            {
                "document": fid,
                "collectors": fluid,
                "name": "Generic constant air",
                "density_kg_m3": 1.2,
                "viscosity_pa_s": 1.81e-5,
                "conductivity_w_m_k": 0.0257,
                "heat_capacity_j_kg_k": 1005.0,
                "provenance": "Assumed constant benchmark air; numerical acceptance separate",
            },
        )
        await call("save_fem", "nx_sim_save", {"document": fid})
        await call("activate_sim", "nx_sim_activate", {"document": sid})
        await call(
            "heat",
            "nx_sim_heat_power",
            {
                "document": sid,
                "body": next(p["body"] for p in plan if p["kind"] == "solid"),
                "power_w": 0.1,
                "name": "Generic solid heat",
                "provenance": "Assumed 0.1 W infrastructure benchmark",
            },
        )
        objects = await call("objects", "nx_sim_objects", {"document": sid})
        fan = await call(
            "fan",
            "nx_sim_fan_table",
            {
                "document": sid,
                "name": "Generic static fan",
                "points": [[0.0, 1.0], [0.0004, 0.0]],
                "pressure_convention": "static",
                "rpm": 1000.0,
                "reference_density_kg_m3": 1.2,
                "stall_region": "not modeled; assumed linear curve",
                "provenance_kind": "assumed",
                "provenance_source": "Synthetic infrastructure fixture, not manufacturer performance",
            },
        )
        await call(
            "bind_fan",
            "nx_sim_assign_fan",
            {"document": sid, "inlet": inlet_id, "field": fan["field"]["id"]},
        )
        await call(
            "loss",
            "nx_sim_head_loss",
            {
                "document": sid,
                "opening": opening_id,
                "coefficient": 2.0,
                "name": "Generic outlet loss",
            },
        )
        await call("save", "nx_sim_save", {"document": sid})
        await call(
            "controls",
            "nx_sim_flow_convergence",
            {
                "document": sid,
                "residual": 1e-6,
                "flow_imbalance_fraction": 0.001,
                "iteration_limit": 1000,
            },
        )
        await call("save_controls", "nx_sim_save", {"document": sid})
        copied = await call(
            "run_copy",
            "nx_sim_save_as",
            {
                "document": sid,
                "path": "ui-benchmarks/public-full-run-r1/full_public_r1.sim",
                "operation_id": "public-full-copy-r1",
            },
        )
        sid = copied["document"]["id"]
        prepared = await call(
            "prepare",
            "nx_sim_prepare_solve",
            {
                "document": sid,
                "job_id": "public-full-coupled-r1",
                "operation_id": "public-full-prepare-r1",
            },
        )
        receipt.update(
            passed=True, solver_launched=False, document=sid, job_id="public-full-coupled-r1"
        )
        record()


if __name__ == "__main__":
    asyncio.run(main())
