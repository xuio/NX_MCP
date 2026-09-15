# Native constant internal-fan flow editing — R3601

The existing `nx_sim_internal_fan_flow` tool passed native authoring/export acceptance on an isolated NX 2606 four-fan Flow SIM. All four flows changed from 0.001179868608 to 0.0016518160512 m³/s (2.5 → 3.5 CFM). Native readback matched each value. Saving/exporting succeeded.

Full XML-tree comparison with the preserved baseline matches after changing only the four Volume Flow values and SIM name. Fan target selections, direction, motor heat, other properties, materials, openings, complete mesh and solver settings are identical. Fan labels retain the old 2P5 suffix; property values govern. Evidence with exact SIM/input hashes is in `tests/simcenter/evidence/native-internal-fan-flow-r3601.json`. Full receipts, archived input and verifier are in the Baldower study R3601.

This adds evidence for the existing tool; no implementation or deployment change was made. It does not validate a vendor operating point, numerical convergence or arbitrary configurations. The configured 14-worker solve is a separate acceptance step.
