/* Offline ABI probe for the pinned 32-bit SpeedTree runtime. Project-authored;
 * no SDK implementation is copied or linked into the game. Invoke with absolute
 * DLL and SPT paths under Wine. This is inspection, not a foliage converter.
 * ABI facts: pinned extern/include/speedtree/SpeedTreeRT.h and PE exports.
 */
#include <windows.h>
#include <stdbool.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void (__attribute__((thiscall)) *ObjectCall)(void *);
typedef bool (__attribute__((thiscall)) *LoadCall)(void *, const char *);
typedef bool (__attribute__((thiscall)) *ComputeCall)(void *, const float *, unsigned, bool);
typedef void (__attribute__((thiscall)) *BoundsCall)(void *, float *);
typedef unsigned (__attribute__((thiscall)) *CountCall)(void *);
typedef const char *(__cdecl *ErrorCall)(void);

static HMODULE library;

/* memcpy avoids nonportable casts between incompatible function pointer types. */
static void resolve(void *destination, const char *name) {
    FARPROC address = GetProcAddress(library, name);
    if (!address) {
        fprintf(stderr, "Missing pinned ABI export: %s\n", name);
        exit(3);
    }
    memcpy(destination, &address, sizeof(address));
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "Usage: speedtree_probe.exe ABSOLUTE_DLL ABSOLUTE_SPT\n");
        return 2;
    }
    if (sizeof(void *) != 4) return 2;
    library = LoadLibraryExA(argv[1], NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!library) {
        fprintf(stderr, "Cannot load pinned runtime: Windows error %lu\n", GetLastError());
        return 3;
    }
    ObjectCall construct, destroy;
    LoadCall load;
    ComputeCall compute;
    BoundsCall bounds;
    CountCall collisions, seed;
    ErrorCall error;
    resolve(&construct, "??0CSpeedTreeRT@@QAE@XZ");
    resolve(&destroy, "??1CSpeedTreeRT@@QAE@XZ");
    resolve(&load, "?LoadTree@CSpeedTreeRT@@QAE_NPBD@Z");
    resolve(&compute, "?Compute@CSpeedTreeRT@@QAE_NPBMI_N@Z");
    resolve(&bounds, "?GetBoundingBox@CSpeedTreeRT@@QBEXPAM@Z");
    resolve(&collisions, "?GetCollisionObjectCount@CSpeedTreeRT@@QAEIXZ");
    resolve(&seed, "?GetSeed@CSpeedTreeRT@@QBEIXZ");
    resolve(&error, "?GetCurrentError@CSpeedTreeRT@@SAPBDXZ");

    /* Deliberately oversized aligned storage; only the DLL owns object layout.
     * The pinned public declaration is smaller than this allocation. */
    void *tree = calloc(1, 4096);
    if (!tree) return 3;
    construct(tree);
    int result = 4;
    if (!load(tree, argv[2])) {
        fprintf(stderr, "LoadTree failed: %s\n", error());
        goto cleanup;
    }
    /* Forest::GetMainTree uses wrapper defaults: seed 1, embedded SPT size.
     * Area::SetTree does not apply property TreeSize/TreeVariance or rotation. */
    if (!compute(tree, NULL, 1, true)) {
        fprintf(stderr, "Compute failed: %s\n", error());
        goto cleanup;
    }
    float extents[6];
    bounds(tree, extents);
    for (unsigned i = 0; i < 6; ++i) {
        if (!isfinite(extents[i]) || fabsf(extents[i]) > 100000.0f) {
            fprintf(stderr, "Invalid computed bound\n");
            goto cleanup;
        }
    }
    for (unsigned i = 0; i < 3; ++i) {
        if (extents[i] >= extents[i + 3]) {
            fprintf(stderr, "Empty computed bounds\n");
            goto cleanup;
        }
    }
    printf("{\"computed\":true,\"seed\":%u,\"collision_objects\":%u,"
           "\"bounds_source\":[%.9g,%.9g,%.9g,%.9g,%.9g,%.9g]}\n",
           seed(tree), collisions(tree), extents[0], extents[1], extents[2],
           extents[3], extents[4], extents[5]);
    result = 0;
cleanup:
    destroy(tree);
    free(tree);
    FreeLibrary(library);
    return result;
}
