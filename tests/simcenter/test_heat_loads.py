import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.heat_loads import create_body_power


@pytest.mark.parametrize("power", [-1, float("nan"), float("inf"), True])
def test_invalid_power_rejected_before_builder(monkeypatch, power):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    sim = NS()
    session = NS(Parts=NS(BaseWork=sim))
    with pytest.raises(NXToolError) as exc:
        create_body_power(session, sim, NS(OwningPart=sim), power, "heat", "assumed")
    assert exc.value.code == "NX_INVALID_ARGUMENT"


def test_unused_existing_target_slot_does_not_block_another_body(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    nx.CAE = cae
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr(
        "nx_mcp.simcenter.heat_overlap.inspect_heat_overlap", lambda sim, targets: []
    )
    existing = NS(
        Name="other source",
        Tag=3,
        PropertyTable=NS(GetPropertyCount=lambda: 1, GetPropertyNameByIndex=lambda i: "Heat Load"),
        TargetSetManager=NS(
            TargetSetCount=1, GetTargetSetMembers=lambda i: (None, [NS(Obj=NS(Tag=1)), None])
        ),
    )
    sim = NS(Simulation=NS(Loads=[existing], Constraints=[]), Expressions=[])

    def reached_mutation(*args):
        raise RuntimeError("preflight passed without dereferencing unused slot")

    session = NS(Parts=NS(BaseWork=sim), SetUndoMark=reached_mutation)
    with pytest.raises(RuntimeError, match="preflight passed"):
        create_body_power(session, sim, NS(OwningPart=sim, Tag=2), 1, "new source", "assumed")
