# Original foliage conversion

The running map still lacks its original trees. Preparation is implemented;
geometry extraction, Blender conversion, materials, wind/billboard behavior,
streaming, collision and exported visual acceptance are incomplete.

Freeze only the current map's foliage dependencies, offline by default:

```sh
python3 tools/prepare_foliage.py \
  --map-manifest .local/map-import/metin2_map_a1/manifest.json \
  --output .local/foliage/my-inputs.json
```

The output must be new. `--online` permits fetching missing pinned inputs.
The tool verifies source Git hashes, reparses original area placements and
property records, resolves tree paths using original pack precedence, and
checks the selected SPT envelope. It does not execute a DLL or claim that an
envelope check establishes valid geometry. Original files and generated receipts
remain ignored. The current Yongan receipt is `.local/foliage-r1/inputs.json`:
14 definitions and 368 placements, all `__IdvSpt_02_`.

The pinned client `GameLib/Area.cpp::__SetObjectInstance_SetTree` passes position,
height bias, CRC and filename only. It does not pass area-object rotations or
property TreeSize/TreeVariance. `SpeedTreeForest.cpp::GetMainTree` invokes
`SpeedTreeWrapper.h::LoadTree` defaults: seed 1 and no size override. Therefore
the prepared records retain rotation/property values for provenance but select
embedded SPT size, seed 1 and unrotated instances. Coordinates use the
existing map adapter, including height bias exactly once. Do not apply the
building transform pipeline blindly to foliage.

`tools/speedtree_probe.c` is a project-authored offline ABI inspection helper
for the pinned 32-bit `bin/SpeedTreeRT.dll`. It resolves constructor, load,
compute, bounds, seed and collision-count exports; it does not patch the DLL,
provide authorization keys or bypass runtime checks. It prints bounded finite
extents only after successful computation. It is not a geometry converter.
The Windows helper compiles with:

```sh
i686-w64-mingw32-gcc -std=c11 -Wall -Wextra -Werror -O2 \
  tools/speedtree_probe.c -o /path/to/ignored/speedtree_probe.exe
```

Compilation passed. Execution was rejected by automatic approval review because
the downloaded DLL is untrusted executable code and a Wine prefix is not a
host-filesystem isolation boundary. No runtime execution occurred. Explicit
user approval is pending for the concrete probe with the pinned DLL and one
selected Beech SPT; this cannot yet be called a working conversion route.
The saved input receipt is `.local/foliage-r1/sources.json`; originals reside
under `assets/source/maps/<client-pin>/`. Any eventual runtime stays outside
client exports. Source availability does not change third-party licensing.

Focused QA: `python -m unittest discover -s tests -p test_foliage_inputs.py`
passes two tests covering malformed envelopes and original coordinate/rotation
policy. Ruff passes both Python files; the C helper passes strict compiler
warnings. These are input/tool checks, not rendered foliage evidence.
