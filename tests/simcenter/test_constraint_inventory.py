from types import SimpleNamespace as NS

from nx_mcp.simcenter.native import SimcenterMixin


def test_compact_and_expanded_constraints_keep_unsupported_targets_explicit():
    class PolygonFace:
        pass

    sim = NS()
    face = PolygonFace()
    face.OwningPart = sim
    members = [NS(Obj=face, SubType=0, SubId=0), None, NS(Obj=None, SubType=1, SubId=19)]
    bc = NS(
        Name="convection",
        Tag=1,
        TargetSetManager=NS(TargetSetCount=1, GetTargetSetMembers=lambda i: (None, members)),
        HasUserAttribute=lambda *args: False,
    )
    sim.Simulation = NS(Constraints=[bc])
    executor = NS(
        session=NS(Parts=NS(BaseWork=sim)),
        objects=NS(resolve=lambda *args, **kwargs: sim),
        nxopen=NS(NXObject=NS(AttributeType=NS(String=0))),
        _reference=lambda value, kind, owner, fallback: {"kind": kind},
    )
    compact = SimcenterMixin._sim_constraints(executor, "sim")
    assert "target_sets" not in compact["constraints"][0]
    assert compact["constraints"][0]["provenance"] is None
    expanded = SimcenterMixin._sim_constraints(executor, "sim", include_targets=True)
    targets = expanded["constraints"][0]["target_sets"][0]
    assert targets["count"] == 2 and targets["members"][0]["face"]["kind"] == "face"
    assert targets["native_slot_count"] == 3 and targets["empty_slot_count"] == 1
    assert targets["members"][1]["reference_status"] == "unsupported_target_kind"
    assert SimcenterMixin._sim_constraints(executor, "sim", offset=1)["constraints"] == []


def test_load_inventory_does_not_read_the_constraints_collection():
    sim = NS()
    load = NS(
        Name="power",
        Tag=2,
        TargetSetManager=NS(TargetSetCount=0),
        HasUserAttribute=lambda *args: False,
    )
    sim.Simulation = NS(Loads=[load])
    executor = NS(
        session=NS(Parts=NS(BaseWork=sim)),
        objects=NS(resolve=lambda *args, **kwargs: sim),
        nxopen=NS(NXObject=NS(AttributeType=NS(String=0))),
        _reference=lambda value, kind, owner, fallback: {"kind": kind},
    )
    result = SimcenterMixin._sim_loads(executor, "sim")
    assert result["loads"][0]["load"]["kind"] == "simulation_load"
    assert result["loads"][0]["energy_accounting"] is None
    assert "constraints" not in result
