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
