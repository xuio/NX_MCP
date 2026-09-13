"""NX 2606 exposes ModelCheck on CAE without an importable dotted module."""

import sys
from enum import IntEnum
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.quality import check_mesh_quality, read_quality_settings


@pytest.fixture
def native(monkeypatch):
    class TestType(IntEnum):
        AspectRatio = 1

    class CriteriaType(IntEnum):
        Warning = 1
        Error = 2

    nx = ModuleType("NXOpen")
    cae = ModuleType("NXOpen.CAE")
    cae.ModelCheck = NS(TestValueTypes=NS(TestType=TestType, CriteriaType=CriteriaType))
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.delitem(sys.modules, "NXOpen.CAE.ModelCheck", raising=False)
    value = NS(
        GetTestType=lambda: TestType.AspectRatio,
        DoTest=True,
        GetValidator=lambda: "LessThan",
        HasCriteriaValue=lambda: True,
        GetCriteriaValue=lambda kind: 10.0 if kind == CriteriaType.Warning else 20.0,
        ElementSpecificTestCount=0,
    )
    setting = NS(
        LimitValueOption="UserDefined", UseElementSpecificValue=False,
        TestValueCount=1, GetTestValueByIndex=lambda i: value,
    )
    return NS(
        GetSolverAndAnalysisType=lambda: ("NX MULTIPHYSICS", "Flow"),
        ElementQualitySettings=NS(GetElementQualitySetting=lambda solver: setting),
    )


def test_reads_native_namespace_without_dotted_import(native):
    settings = read_quality_settings(native)
    assert settings["tests"] == [{
        "test_type": "AspectRatio", "enabled": True, "validator": "LessThan",
        "has_criteria": True, "criteria": {"Warning": 10.0, "Error": 20.0},
        "specific_count": 0,
    }]


def test_executes_quality_checks_and_preserves_failures(native):
    events = []
    result = NS(
        ElementTestCount=12,
        GetTestSummary=lambda: [NS(
            TestType=1, TestCount=12, ErrorCount=1, WarnedCount=2,
            WorstTestValue=25.0, HasTestValue=True,
        )],
        Dispose=lambda: events.append("dispose"),
    )
    mesh = NS(OwningPart=native)
    builder = NS(
        SelectionList=NS(Add=lambda meshes: events.append(meshes)),
        ExecuteCheck=lambda: result, CheckScopeOption="SelectedMeshes",
        Destroy=lambda: events.append("destroy"),
    )
    native.ModelCheckMgr = NS(CreateElementQualityCheckBuilder=lambda: builder)
    checked = check_mesh_quality(native, [mesh])
    assert checked["element_count"] == 12
    assert checked["tests"][0]["errors"] == 1
    assert checked["tests"][0]["warnings"] == 2
    assert checked["tests"][0]["worst_value"] == 25.0
    assert not checked["repair_attempted"]
    assert events == [[mesh], "dispose", "destroy"]
