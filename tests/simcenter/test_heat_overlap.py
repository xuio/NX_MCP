from nx_mcp.simcenter.heat_overlap import conflicts


def test_body_and_its_face_conflict_in_both_directions():
    body, face = ("body", 10, 10), ("face", 20, 10)
    assert conflicts(body, face) and conflicts(face, body)


def test_different_faces_allow_separate_heat_sources():
    assert not conflicts(("face", 20, 10), ("face", 21, 10))


def test_distinct_bodies_do_not_imply_overlap():
    assert not conflicts(("body", 10, 10), ("face", 21, 11))


def test_same_face_conflicts():
    assert conflicts(("face", 20, 10), ("face", 20, 10))
