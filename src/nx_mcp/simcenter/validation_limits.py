"""Finite validation ceilings shared by input and mesh lifecycle checks.

Defaults remain small; callers must explicitly request larger mesh traversals.
These ceilings do not establish solve readiness or numerical validity.
"""

MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_MESH_ENTITIES = 2_000_000
