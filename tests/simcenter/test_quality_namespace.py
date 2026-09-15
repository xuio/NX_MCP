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


def test_native_report_export_and_existing_file_preserved(native, tmp_path):
    import hashlib
    from pathlib import Path

    from nx_mcp.runtime import NXToolError

    events = []
    mc = sys.modules['NXOpen.CAE'].ModelCheck
    mc.ElementQualityCheckBuilder = NS(ReportFormat=NS(FailedAndWarning=7))
    result = NS(ElementTestCount=12, GetTestSummary=lambda: [], Dispose=lambda: events.append('dispose'))
    builder = NS(SelectionList=NS(Add=lambda meshes: None), ExecuteCheck=lambda: result,
                 CheckScopeOption='SelectedMeshes', Destroy=lambda: events.append('destroy'),
                 WriteResultsToFile=lambda path, data: Path(path).write_text('Failed element 42\n'))
    native.ModelCheckMgr = NS(CreateElementQualityCheckBuilder=lambda: builder)
    mesh = NS(OwningPart=native)
    path = tmp_path/'failed.txt'
    checked = check_mesh_quality(native, [mesh], report_path=path)
    assert builder.ElementReportFormat == 7
    assert checked['report']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert checked['report']['bytes'] == path.stat().st_size
    assert events == ['dispose','destroy']
    with pytest.raises(NXToolError):
        check_mesh_quality(native, [mesh], report_path=path)
    assert path.read_text() == 'Failed element 42\n'
    assert events == ['dispose','destroy']


@pytest.mark.parametrize('name', ['source.prt', 'absent/report.txt'])
def test_report_rejects_wrong_suffix_or_missing_parent_before_native_check(native, tmp_path, name):
    from nx_mcp.runtime import NXToolError

    with pytest.raises(NXToolError):
        check_mesh_quality(native, [NS(OwningPart=native)], report_path=tmp_path/name)


@pytest.mark.parametrize('labels', [[], [0], [True], [1,1], ['1'], list(range(1,1002))])
def test_element_query_rejects_unbounded_or_ambiguous_selection(labels):
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.quality import inspect_elements

    with pytest.raises(NXToolError):
        inspect_elements(None, labels)


def test_element_query_preserves_order_and_disposes_on_missing_label():
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.quality import inspect_elements

    events = []
    nodes = [NS(Label=i+1,Coordinates=NS(X=x,Y=y,Z=z)) for i,(x,y,z) in
             enumerate([(0,0,0),(2,0,0),(0,2,0),(0,0,2)])]
    mesh = NS(JournalIdentifier='Mesh[1]',MeshCollector=NS(JournalIdentifier='Collector[1]'))
    element = NS(Label=42,Shape='Tet',Mesh=mesh,GetNodes=lambda: nodes)
    label_map = NS(GetElement=lambda n: element if n==42 else None,Dispose=lambda: events.append('dispose'))
    fem = NS(BaseFEModel=NS(FeelementLabelMap=label_map),FullPath='test.fem')
    checked = inspect_elements(fem,[42])
    assert checked['elements'][0]['vertex_average_mm']==[.5,.5,.5]
    assert [n['label'] for n in checked['elements'][0]['nodes']]==[1,2,3,4]
    assert not checked['mesh_modified'] and events==['dispose']
    with pytest.raises(NXToolError):
        inspect_elements(fem,[43])
    assert events==['dispose','dispose']
