# Original map data: verified sample

This records the initial source inspection. The subsequent automated conversion
and shared client/server collision bake are documented in
[map importing](map-import.md). Statements below about pending format work refer
to that initial sample, not the current implementation; current gameplay/export
evidence is in [distribution](distribution.md#verification-status).

Inspected on 2026-09-06 at client archive commit
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`. The archive contains concrete
terrain and object-placement data suitable for developing an importer. This
inspection verifies selected records and dependencies, not complete map rendering
or the availability of every asset in every patch.

The inspected map is `bin/pack/OutdoorA1/metin2_map_a1`. Its
[settings](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/OutdoorA1/metin2_map_a1/setting.txt)
declare a 4 by 5 section layout, height scale 0.5, a map base position, texture
set and environment reference. The directory lists all 20 corresponding section
directories. References use legacy path conventions and capitalization that the
importer must normalize.

| Data | Observed files | What it supplies |
| --- | --- | --- |
| Terrain elevation | `height.raw` | Height samples interpreted by the original terrain reader |
| Terrain surface layers | `tile.raw`, `textureset/metin2_a1.txt` | Layer indices and texture references/settings; the inspected texture set has 17 entries |
| Placed scenery | `areadata.txt` | Object positions, property IDs, rotation fields and height bias |
| Property definitions | `Property/property/a/01/*.prb` | Building property IDs mapped to GR2 model paths |
| Terrain attributes | `attr.atr` | Per-cell attribute data; exact flags and server behavior require further validation |
| Water | `water.wtr` | Water-map data loaded by the original terrain code |
| Supporting visuals | `minimap.dds`, `shadowmap.dds`, `shadowmap.raw` | Minimap and shadow resources listed in inspected sections |

Two section inventories (`000000`, `001002`) each contain the ten expected files
observed in this sample. Listing a file establishes availability, not that our
converter supports its contents.

## A verified placement-to-model chain

Section `001002` contains 97 placement records. Section `002002` contains 184.
In the latter's
[placement data](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/OutdoorA1/metin2_map_a1/002002/areadata.txt),
object 182 has property ID `4285160494`, source position
`(68620.945313, -56243.625, 19892.332031)`, and rotation fields
`0 / 0 / 300`.

The matching
[item-shop property](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/Property/property/a/01/a1-007-itemshop.prb)
identifies `d:/ymir work/zone/a/building/a1-007-itemshop.gr2`. The archive's
[building directory](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/Zone/ymir%20work/zone/a/building)
lists that model at 50,234 bytes. House, bank and bridge model entries were also
located. The models and their full material dependencies were not imported.

These coordinates and rotations are source values. Conversion must follow the
original transform conventions before mapping them into Godot axes and units.
The original
[Area.cpp](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/Area.cpp)
reads placement records, resolves property IDs, applies rotations and height
bias, and constructs the building instances. This gives an implementation
reference for the conversion.

## Terrain sample and provenance

The downloaded `001002/height.raw` sample is 34,322 bytes, or 17,161 16-bit
samples: a 131 by 131 raw grid. Its size/type agrees with the original
[terrain reader](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/PRTerrainLib/Terrain.cpp)
and
[dimension definitions](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/PRTerrainLib/Terrain.h).
Height samples were decoded for inspection; terrain geometry, border handling,
normals and visual fidelity have not been tested in Godot.

Small source/text samples and directory metadata are cached under
`.cache/metin-map-research/`, outside the gameplay asset fixture. Every downloaded
file sample was checked against its Git blob SHA. No building models were
downloaded, no original code was executed, and no map has been converted into
the current client by this inspection.

Next, audit a complete representative section's dependency closure, including
textures, collision resources and effects. Separately audit server map/spawn
data and gameplay definitions; the client sample does not establish their
completeness. Continue with the [rebuild roadmap](full-rebuild-plan.md).
