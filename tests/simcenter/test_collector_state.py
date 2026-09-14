from types import SimpleNamespace as NS

from nx_mcp.simcenter.collector_state import inspect_collector, state_hash


def test_state_hash_tracks_assignment_frame_and_owner_generation():
    base = {"collector": {"id": "a", "generation_id": "one"}, "material": "m", "frame": [1, 0, 0]}
    assert state_hash(base) == state_hash(dict(reversed(list(base.items()))))
    for field, value in [
        ("material", "other"),
        ("frame", [0, 1, 0]),
        ("collector", {"id": "a", "generation_id": "two"}),
    ]:
        assert state_hash({**base, field: value}) != state_hash(base)


def test_failed_inspection_disposes_assignment_and_omits_edit_hash():
    disposed = []

    class Assignment:
        @property
        def Material(self):
            raise RuntimeError("native read failure")

        def Dispose(self):
            disposed.append(True)

    table = NS(GetPhysicalMaterialPropertyValue=lambda _: Assignment())
    collector = NS(
        CollectorNeutralType="Solid",
        ElementPropertyTable=NS(
            GetNamedPropertyTablePropertyValue=lambda _: NS(PropertyTable=table)
        ),
    )
    row = inspect_collector(None, collector, lambda *args: {"id": "collector"}, "mm")
    assert disposed == [True]
    assert "state_sha256" not in row
    assert row["inspection_error"]["status"] == "read_failed"


def test_fluid_collector_is_explicitly_unsupported_without_native_solid_access():
    row = inspect_collector(
        None, NS(CollectorNeutralType="Fluid"), lambda *args: {"id": "collector"}, "mm"
    )
    assert row["assignment_inspection"] == "unsupported_collector_type"
    assert "state_sha256" not in row


def test_membership_uses_native_owner_not_collection_order(monkeypatch):
    from nx_mcp.simcenter import collector_state as module

    collectors = [NS(Tag=22), NS(Tag=11)]
    meshes = [NS(Tag=1, MeshCollector=collectors[1]), NS(Tag=2, MeshCollector=collectors[0])]
    fem = NS(
        BaseFEModel=NS(
            MeshManager=NS(GetMeshCollectors=lambda: collectors, GetMeshes=lambda: meshes)
        )
    )
    monkeypatch.setattr(
        module, "inspect_collector", lambda fem, c, ref, units: {"state_sha256": str(c.Tag)}
    )
    rows = module.inspect_collectors(fem, lambda obj, *args: {"id": str(obj.Tag)}, "mm")[
        "collectors"
    ]
    assert rows[0]["meshes"] == [{"id": "2"}]
    assert rows[1]["meshes"] == [{"id": "1"}]
    assert rows[0]["state_sha256"] == "22"
    assert all(r["membership_status"] == "complete" for r in rows)
    paged = module.inspect_collectors(
        fem, lambda obj, *args: {"id": str(obj.Tag)}, "mm", offset=1, limit=1
    )
    assert paged["collectors"][0]["meshes"] == [{"id": "1"}]


def test_membership_failure_never_returns_partial_mapping(monkeypatch):
    from nx_mcp.simcenter import collector_state as module

    collector = NS(Tag=1)
    meshes = [NS(Tag=2, MeshCollector=collector), NS(Tag=3)]
    fem = NS(
        BaseFEModel=NS(
            MeshManager=NS(GetMeshCollectors=lambda: [collector], GetMeshes=lambda: meshes)
        )
    )
    monkeypatch.setattr(module, "inspect_collector", lambda *args: {"state_sha256": "preserved"})
    row = module.inspect_collectors(fem, lambda obj, *args: {"id": str(obj.Tag)}, "mm")[
        "collectors"
    ][0]
    assert row["membership_status"] == "read_failed"
    assert "meshes" not in row
    assert row["state_sha256"] == "preserved"
