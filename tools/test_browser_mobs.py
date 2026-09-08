"""Population evidence from the actual exported clients' subscribed snapshots."""

import math
from collections import Counter


def population_summary(web, native, catalog):
    expected = {int(mob["vnum"]) for mob in catalog["mobs"]}
    observed = []
    counts = []
    for snapshot in (web, native):
        ids = {}
        for row in snapshot["monsters"]:
            if int(row["id"]) == 900001:  # Independent authored practice dummy.
                continue
            identity, vnum = int(row["id"]), int(row["definition_vnum"])
            assert identity > 900001 and identity not in ids, "Invalid or duplicate mob ID"
            assert vnum in expected, "Unregistered mob species"
            assert all(math.isfinite(row[key]) for key in ("x", "y", "z")), "Invalid mob position"
            ids[identity] = vnum
        assert len(ids) > 2000, "Expected full original Yongan population"
        assert set(ids.values()) == expected, "Original species missing from subscription"
        observed.append(ids)
        counts.append(dict(sorted(Counter(ids.values()).items())))
    assert observed[0] == observed[1], "Exported clients received different mob populations"
    return {"count": len(observed[0]), "species": len(expected), "species_counts": counts[0]}
