#!/usr/bin/env python3
"""Compile the pinned original drop tables into one deterministic JSON corpus.

The corpus is read straight out of the pinned ``git.old-metin2.com`` server tree
and no game code is executed.  Three files drive loot in the original:

* ``gamefiles/data/common_drop_item.txt`` - per-mob-rank level bands shared by
  every monster (``ITEM_MANAGER::ReadCommonDropItemFile``).
* ``gamefiles/data/mob_drop_item.txt`` - per-mob ``drop`` / ``kill`` / ``limit`` /
  ``thiefgloves`` groups (``ITEM_MANAGER::ReadMonsterDropItemGroup``).
* ``gamefiles/conf/item_proto.txt`` - item prototypes used to resolve names.

Both readers are reproduced as closely as the source allows, including the
quirks that decide which vnums and percentages a running server would have had:

* ``CTextFileLoader::LoadGroup`` lowercases the *leading* token of every row, so
  keys are ``type``/``mob``/``kill_drop``/``level_limit`` and the numeric row
  keys ``1``..``255`` regardless of the file's own capitalisation.  Rows live in
  a ``std::map`` inserted with ``insert`` (first row wins for a duplicated key)
  while group children live in a ``std::vector`` (a duplicated group name is a
  second node, not a replacement).
* ``GetCurrentNodeName`` returns false while the loader sits on the global node,
  because that node has no parent - so the ``kr_`` prefix skip in
  ``ReadMonsterDropItemGroup`` never fires.  It is dead code in the pinned
  revision, which is also why ``mob_drop_item.txt`` contains no ``kr_`` group.
* a ``kill`` row's percentage is a *raw integer* percent (``strtol``) and the
  rare percent is clamped to ``0..100``; ``drop``/``limit``/``thiefgloves`` rows
  read only three values and scale a ``float`` percent by 10000 in IEEE-754
  binary32, truncating toward zero.
* the common-drop walk shares a single tab cursor across the six fields of each
  of the four rank blocks, so a missing tab leaves that block and every later
  block at the line's zeroed defaults.
* that same cursor makes 29 pinned common-drop lines unreadable as authored.
  Lines 436-459 carry 19 tabs instead of the 24 fields the reader expects (the
  author dropped the per-block label column) and lines 536-540 pad the first two
  blocks instead of the first three, so the reader shifts every later field one
  column left.  The result is a band whose ``iLevelStart`` (8000, 16000, 32000,
  80000, 160000, 320000, 66666666, ...) is far above the level cap, so the row
  is *loaded but never selectable*: ``CreateDropItem`` skips it with
  ``iLevel < c_rInfo.m_iLevelStart``.  The corpus keeps those rows verbatim and
  marks them ``reachable: false`` instead of silently repairing the table, so
  the rebuild cannot hand out a drop the original server never gave.
* item names resolve to the *first* prototype (vnum ascending, as sorted by
  ``CClientManager::InitializeItemTable``) whose stored name - truncated to
  ``ITEM_NAME_MAX_LEN`` = 24 bytes - starts with the token, compared by
  ``strncasecmp`` with C-locale folding (ASCII only).  An empty token matches
  the first prototype, which is how the file's header line is accepted.
* a row that cannot resolve an item aborts the whole load with ``return false``
  in the original.  These files load cleanly there, so an unresolvable row here
  is reported as an error and the corpus build fails instead of silently
  dropping loot.

Usage::

    python3 tools/metin_drops.py --summary
    python3 tools/metin_drops.py --output .local/drops/corpus.v2.json
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / ".cache/full-game-research/server/source"
COMMON_DROP = Path("gamefiles/data/common_drop_item.txt")
MOB_DROP = Path("gamefiles/data/mob_drop_item.txt")
ITEM_PROTO = Path("gamefiles/conf/item_proto.txt")

SCHEMA = "mt2spacetime.drop-corpus"
VERSION = 2

# ``EMobRank`` in the pinned ``common/length.h``. Only the first four ranks
# receive common-drop rows (``ReadCommonDropItemFile`` fills
# ``i <= MOB_RANK_S_KNIGHT``), but the whole enum is carried because the mob
# catalog and the drop catalog have to agree on what a rank number means.
MOB_RANKS = ("PAWN", "S_PAWN", "KNIGHT", "S_KNIGHT", "BOSS", "KING")
RANKS = MOB_RANKS[:4]
GROUP_TYPES = ("drop", "kill", "limit", "thiefgloves")

ITEM_NAME_MAX_LEN = 24  # itemTable->szName[ITEM_NAME_MAX_LEN + 1]
DELIMITERS = b" \t"
FGETS_BUFFER = 1024
STRLCPY_TEMP = 64
ROW_KEY_LIMIT = 255
# ``PLAYER_MAX_LEVEL_CONST`` (``src/common/length.h``); ``conf.txt``'s
# ``PLAYER_MAX_LEVEL`` is clamped to ``1..120`` and the rebuild keeps the same
# cap, so a common row whose band cannot contain any level in that range never
# rolls - which is exactly what happens to the malformed lines above.
PLAYER_MAX_LEVEL = 120


class DropCorpusError(RuntimeError):
    """The pinned input would have aborted the original loader."""


# ---------------------------------------------------------------------------
# libc helpers
# ---------------------------------------------------------------------------


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(value: float) -> float:
    """Round through IEEE-754 binary32 (the original computes in ``float``)."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def c_atof(text: bytes) -> float:
    """``atof`` on a NUL-terminated string: longest valid numeric prefix."""
    raw = text.decode("latin-1").strip()
    end = 0
    seen_digit = False
    seen_dot = False
    seen_exp = False
    while end < len(raw):
        char = raw[end]
        if char in "+-" and end == 0:
            end += 1
            continue
        if char.isdigit():
            seen_digit = True
            end += 1
            continue
        if char == "." and not seen_dot:
            seen_dot = True
            end += 1
            continue
        if char in "eE" and seen_digit and not seen_exp:
            seen_exp = True
            end += 1
            if end < len(raw) and raw[end] in "+-":
                end += 1
            continue
        break
    if not seen_digit:
        return 0.0
    try:
        return float(raw[:end])
    except ValueError:
        return 0.0


def _c_strtoint(text: bytes, signed: bool) -> int | None:
    """``strtol``/``strtoul`` base 10 with ``NULL`` end pointer.

    Returns ``None`` when no conversion happens (the caller's ``str_to_number``
    returns false and leaves the destination untouched).
    """
    raw = text.decode("latin-1")
    index = 0
    while index < len(raw) and raw[index] in " \t\n\r\v\f":
        index += 1
    start = index
    if index < len(raw) and raw[index] in "+-":
        if not signed and raw[index] == "-":
            pass  # strtoul negates modulo 2**32 below
        index += 1
    digits = index
    while index < len(raw) and raw[index].isdigit() and raw[index].isascii():
        index += 1
    if index == digits:
        return None
    value = int(raw[start:index], 10)
    if not signed:
        return value & 0xFFFFFFFF
    return value


def c_strtol10(text: bytes) -> int:
    """``strtol(in, NULL, 10)`` with the original's 0-on-failure default."""
    value = _c_strtoint(text, signed=True)
    return 0 if value is None else value


def c_strtoul10(text: bytes) -> int:
    """``strtoul(in, NULL, 10)`` (``str_to_number(DWORD&)``)."""
    value = _c_strtoint(text, signed=False)
    return 0 if value is None else value


def percent_to_10k(text: bytes) -> int:
    """``(DWORD)(10000.0f * fPercent)`` - binary32 rounding, then truncation."""
    return int(f32(f32(c_atof(text)) * f32(10000.0)))


def ascii_lower_byte(byte: int) -> int:
    return byte + 32 if 0x41 <= byte <= 0x5A else byte


def stl_lowers(token: bytes) -> bytes:
    """``stl_lowers``: ``tolower`` per byte, C locale (ASCII A-Z only)."""
    return bytes(ascii_lower_byte(byte) for byte in token)


def strncasecmp_prefix(token: bytes, name: bytes) -> bool:
    """``strncasecmp(token, name, len(token)) == 0`` for NUL-terminated names."""
    if len(name) < len(token):
        # ``name`` ends in NUL before the token does, so the comparison differs.
        return False
    # The length precondition above already fixed the comparison count, so the
    # shorter sequence must not be treated as an error.
    return all(
        ascii_lower_byte(left) == ascii_lower_byte(right)
        for left, right in zip(token, name, strict=False)
    )


def strlcpy(text: bytes, size: int) -> bytes:
    """``strlcpy`` semantics: at most ``size - 1`` bytes, always NUL-bounded."""
    return bytes(text[: max(size - 1, 0)])


def decode_original_text(raw: bytes) -> str:
    """Keep a CP949 table name JSON-safe without claiming a decoded charset.

    The pinned tables store their names in CP949.  The corpus preserves the raw
    bytes as Latin-1 code points, so ``value.encode("latin-1")`` recovers the
    exact source bytes and every emitted string stays well formed.
    """
    return raw.decode("latin-1")


# ---------------------------------------------------------------------------
# CMemoryTextFileLoader / CTextFileLoader emulation
# ---------------------------------------------------------------------------


def bind_lines(data: bytes) -> list[bytes]:
    """``CMemoryTextFileLoader::Bind``.

    A newline (or carriage return) ends a line and consumes one immediately
    following break character; high-bit bytes are copied in pairs, which is how
    the loader keeps CP949 lead/trail bytes intact.
    """
    lines: list[bytes] = []
    line = bytearray()
    position = 0
    size = len(data)
    while position < size:
        char = data[position]
        position += 1
        if char in (0x0A, 0x0D):
            if position < size and data[position] in (0x0A, 0x0D):
                position += 1
            lines.append(bytes(line))
            line = bytearray()
        elif char >= 0x80:
            line += data[position - 1 : position + 1]
            position += 1
        else:
            line.append(char)
    lines.append(bytes(line))
    return lines


def split_line(line: bytes, delimiters: bytes = DELIMITERS) -> list[bytes] | None:
    """``CMemoryTextFileLoader::SplitLine``; ``None`` mirrors its ``false``."""
    tokens: list[bytes] = []
    length = len(line)
    base = 0
    while True:
        begin = base
        while begin < length and line[begin] in delimiters:
            begin += 1
        if begin >= length:
            return None
        if line[begin] == 0x23 and line[begin : begin + 4] != b"#--#":
            return None
        if line[begin] == 0x22:
            begin += 1
            end = line.find(b'"', begin)
            if end < 0:
                return None
            base = end + 1
        else:
            end = begin
            while end < length and line[end] not in delimiters:
                end += 1
            base = end
        tokens.append(line[begin:end])
        probe = base
        while probe < length and line[probe] in delimiters:
            probe += 1
        if probe >= length:
            break
        if base >= length:
            break
    return tokens


class GroupNode:
    """One ``CTextFileLoader::TGroupNode``."""

    __slots__ = ("name", "parent", "children", "tokens", "lines", "line")

    def __init__(self, name: bytes, parent: "GroupNode | None") -> None:
        self.name = name
        self.parent = parent
        self.children: list[GroupNode] = []
        self.tokens: dict[bytes, list[bytes]] = {}
        # 1-based source line of each stored row, for diagnostics only.
        self.lines: dict[bytes, int] = {}
        # 1-based source line of the ``group`` header, for diagnostics only.
        self.line = 0


class TextFileLoader:
    """``CTextFileLoader`` limited to what the drop readers use."""

    def __init__(self, data: bytes, label: str) -> None:
        self.label = label
        self.lines = bind_lines(data)
        self.index = 0
        self.root = GroupNode(b"global", None)
        self.current = self.root
        self.load_group(self.root)

    # -- parsing ----------------------------------------------------------
    def load_group(self, node: GroupNode) -> None:
        while self.index < len(self.lines):
            tokens = split_line(self.lines[self.index])
            if not tokens:
                self.index += 1
                continue
            tokens[0] = stl_lowers(tokens[0])
            head = tokens[0]
            if head[:1] == b"{":
                self.index += 1
                continue
            if head[:1] == b"}":
                break
            if head == b"group":
                if len(tokens) != 2:
                    raise DropCorpusError(
                        f"{self.label}:{self.index + 1}: invalid group syntax "
                        f"({len(tokens)} tokens, spaces are not allowed in names)"
                    )
                child = GroupNode(stl_lowers(tokens[1]), node)
                child.line = self.index + 1
                node.children.append(child)
                self.index += 1
                self.load_group(child)
                self.index += 1  # the caller's loop increments past the brace
                continue
            if head == b"list":
                if len(tokens) != 2:
                    self.index += 1
                    continue
                key = stl_lowers(tokens[1])
                values: list[bytes] = []
                line = self.index + 1
                self.index += 1
                while self.index < len(self.lines):
                    sub = split_line(self.lines[self.index])
                    if not sub:
                        self.index += 1
                        continue
                    if sub[0][:1] == b"{":
                        self.index += 1
                        continue
                    if sub[0][:1] == b"}":
                        break
                    values.extend(sub)
                    self.index += 1
                node.tokens.setdefault(key, values)
                node.lines.setdefault(key, line)
                self.index += 1
                continue
            if len(tokens) == 1:
                # ``LoadGroup`` logs "must have a value" and ``break``s without
                # advancing the line index, so every enclosing ``LoadGroup``
                # re-reads the same line, breaks in turn and the file stops
                # being parsed at this point.  The pinned tables contain no such
                # line (their only one-token lines are ``{``/``}``), so this is
                # reported instead of silently truncating the corpus.
                raise DropCorpusError(
                    f"{self.label}:{self.index + 1}: row {tokens[0]!r} has no value; "
                    "the original loader would stop parsing the rest of the file here"
                )
            node.tokens.setdefault(head, tokens[1:])
            node.lines.setdefault(head, self.index + 1)
            self.index += 1

    # -- navigation -------------------------------------------------------
    def set_top(self) -> None:
        self.current = self.root

    def child_count(self) -> int:
        return len(self.current.children)

    def set_child_node(self, index: int) -> None:
        self.current = self.current.children[index]

    def set_parent_node(self) -> None:
        assert self.current.parent is not None
        self.current = self.current.parent

    def current_node_name(self) -> bytes | None:
        """``GetCurrentNodeName``; ``None`` on the parentless global node."""
        if self.current.parent is None:
            return None
        return self.current.name

    def token(self, key: bytes) -> list[bytes] | None:
        return self.current.tokens.get(key)

    def token_string(self, key: bytes) -> bytes | None:
        values = self.token(key)
        if not values:
            return None
        return values[0]

    def token_integer(self, key: bytes) -> int | None:
        """``GetTokenInteger``: ``None`` when the key or its value is missing.

        A present-but-empty value is impossible outside quoted fields; if one
        ever appeared, ``str_to_number`` would leave the caller's zeroed
        destination alone and the call would still report success.
        """
        values = self.token(key)
        if not values:
            return None
        return c_strtol10(values[0])


# ---------------------------------------------------------------------------
# ITEM_MANAGER prototype table
# ---------------------------------------------------------------------------


CSV_LINE_BUFFER = 2048
DWORD_MASK = 0xFFFFFFFF


class ItemPrototype(NamedTuple):
    vnum: int
    name: bytes
    vnum_range: int


def csv_rows(data: bytes) -> list[list[bytes]]:
    """``cCsvFile::Load(..., '\\t')``: trimmed lines, ``#`` comments skipped.

    The reader trims *whole lines* only, so a field keeps its own leading
    spaces; it is the field text that reaches ``str_to_number``/``atof``.
    Quote handling is not modelled because the pinned file contains none.
    """
    if b'"' in data:
        raise DropCorpusError(
            "item_proto.txt contains quote characters; the CSV reader's quoted "
            "field handling is deliberately not implemented"
        )
    rows: list[list[bytes]] = []
    for number, line in enumerate(data.split(b"\n"), start=1):
        if len(line) + 1 >= CSV_LINE_BUFFER:
            raise DropCorpusError(
                f"item_proto.txt line {number} is {len(line)} bytes and would be "
                f"split by the reader's {CSV_LINE_BUFFER} byte buffer"
            )
        text = line.strip(b" \t\r\n")
        if not text or text.startswith(b"#"):
            continue
        rows.append(text.split(b"\t"))
    return rows


def load_item_table(data: bytes) -> "ItemTable":
    """``Set_Proto_Item_Table`` for the two columns drop tables depend on."""
    rows = csv_rows(data)
    if not rows:
        raise DropCorpusError("item_proto.txt is empty")

    prototypes: list[ItemPrototype] = []
    for number, columns in enumerate(rows[1:], start=2):
        if len(columns) < 2:
            raise DropCorpusError(f"item_proto.txt line {number}: {len(columns)} column(s)")

        raw_vnum = columns[0]
        tilde = raw_vnum.find(b"~")
        if tilde < 0:
            vnum = c_strtol10(raw_vnum) & DWORD_MASK
            vnum_range = 0
        else:
            start = c_strtol10(raw_vnum[:tilde])
            end = c_strtol10(raw_vnum[tilde + 1 :])
            if start == 0 or (end != 0 and end < start):
                raise DropCorpusError(f"item_proto.txt line {number}: INVALID VNUM {raw_vnum!r}")
            vnum = start & DWORD_MASK
            vnum_range = (end - start) & DWORD_MASK

        prototypes.append(
            ItemPrototype(
                vnum=vnum,
                name=strlcpy(columns[1], ITEM_NAME_MAX_LEN + 1),
                vnum_range=vnum_range,
            )
        )

    return ItemTable(prototypes)


class ItemTable:
    """The prototype array as the game server receives it.

    ``CClientManager::InitializeItemTable`` sorts ``m_vec_itemTable`` by
    ``dwVnum`` (``FCompareVnum``) before the table is shipped to the game
    server, so ``GetVnumByOriginalName`` walks vnum-ascending rows and
    ``RealNumber`` binary searches the same order.
    """

    def __init__(self, prototypes: list[ItemPrototype]) -> None:
        self.prototypes = sorted(prototypes, key=lambda row: row.vnum)
        seen: set[int] = set()
        for row in self.prototypes:
            if row.vnum in seen:
                # ``FCompareVnum`` only compares vnums, so ``std::sort`` leaves
                # equal rows in an unspecified order and the real lookup would
                # depend on the sort implementation.
                raise DropCorpusError(f"item_proto.txt repeats vnum {row.vnum}")
            seen.add(row.vnum)
        self.range_rows = [row for row in self.prototypes if row.vnum_range != 0]
        self._vnums = [row.vnum for row in self.prototypes]
        # ``strncasecmp(token, name, len(token))`` can only agree when the first
        # bytes fold together, so the expensive name scan is limited to the
        # bucket of the token's first byte.  Rows keep their vnum order inside a
        # bucket, which preserves which prototype wins.
        buckets: dict[int, list[ItemPrototype]] = {}
        for row in self.prototypes:
            if not row.name:
                continue  # an empty stored name only ever matches an empty token
            buckets.setdefault(ascii_lower_byte(row.name[0]), []).append(row)
        self._name_buckets = buckets

    def __len__(self) -> int:
        return len(self.prototypes)

    def by_original_name(self, token: bytes) -> int | None:
        """``GetVnumByOriginalName``: first ``strncasecmp`` prefix match wins."""
        if not token:
            return self.prototypes[0].vnum
        for row in self._name_buckets.get(ascii_lower_byte(token[0]), ()):
            if strncasecmp_prefix(token, row.name):
                return row.vnum
        return None

    def contains(self, vnum: int) -> bool:
        """``GetTable(vnum) != NULL``: exact hit, else the range rows."""
        index = bisect.bisect_left(self._vnums, vnum)
        if index < len(self._vnums) and self._vnums[index] == vnum:
            return True
        for row in self.range_rows:
            upper = (row.vnum + row.vnum_range) & DWORD_MASK
            if row.vnum < vnum < upper:
                return True
        return False

    def resolve(self, token: bytes) -> int | None:
        """``GetVnumByOriginalName`` with the readers' numeric fallback.

        ``None`` means the original loader would log "No such an item" and
        abort the whole file with ``return false``.
        """
        found = self.by_original_name(token)
        if found is not None:
            return found
        # ``str_to_number(DWORD&)`` leaves the destination untouched on failure,
        # and both readers initialise it to 0 before the fallback.
        numeric = c_strtoul10(token)
        if self.contains(numeric):
            return numeric
        return None

    def identity(self) -> str:
        """Digest of the shipped prototype rows (vnum, range and stored name)."""
        digest = hashlib.sha256()
        for row in self.prototypes:
            digest.update(f"{row.vnum}\t{row.vnum_range}\t".encode("ascii"))
            digest.update(row.name)
            digest.update(b"\n")
        return digest.hexdigest()


# ---------------------------------------------------------------------------
# ReadCommonDropItemFile
# ---------------------------------------------------------------------------


def fgets_chunks(data: bytes) -> list[bytes]:
    """``while (fgets(buf, 1024, fp))``: at most 1023 bytes, newline kept."""
    chunks: list[bytes] = []
    position = 0
    size = len(data)
    while position < size:
        newline = data.find(b"\n", position)
        stop = size if newline < 0 else newline + 1
        if stop - position > FGETS_BUFFER - 1:
            stop = position + FGETS_BUFFER - 1
        chunks.append(data[position:stop])
        position = stop
    return chunks


def percent_to_10k_value(percent: float) -> int:
    """``(DWORD)(fPercent * 10000.0f)`` in binary32, truncating toward zero."""
    return int(f32(f32(percent) * f32(10000.0)))


def parse_common_drop(
    data: bytes, items: ItemTable, label: str
) -> tuple[dict[str, list[dict]], dict]:
    """``ITEM_MANAGER::ReadCommonDropItemFile`` over the pinned table."""
    ranks: dict[str, list[dict]] = {rank: [] for rank in RANKS}
    stats: dict = {
        "lines": 0,
        "rows_kept": 0,
        "skipped_level_start_zero": 0,
        "resolved_by_number": 0,
        "empty_name_resolutions": 0,
        "max_player_level": PLAYER_MAX_LEVEL,
        "unreachable_rows": 0,
        "unreachable_by_rank": {rank: 0 for rank in RANKS},
        "unreachable_lines": [],
        "clamped_level_end_rows": 0,
    }
    unreachable_lines: set[int] = set()

    for number, chunk in enumerate(fgets_chunks(data), start=1):
        stats["lines"] += 1
        # ``fgets`` hands the reader a NUL-terminated C string.
        text = chunk.split(b"\x00", 1)[0]
        if not text or text.startswith(b"\n"):
            continue

        blocks = [
            {"lv_start": 0, "lv_end": 0, "percent": 0.0, "name": b"", "count": 0} for _ in RANKS
        ]

        cursor = 0
        for index in range(len(RANKS)):
            # The original reads ``d[i]`` after its field loop, so a block that
            # never reaches a field keeps the zeroed defaults of *its own*
            # struct - not the previous block's values.
            block = blocks[index]
            for field in range(6):
                tab = text.find(b"\t", cursor)
                if tab < 0:
                    break
                # ``strlcpy(szTemp, p, min(64, (p2 - p) + 1))``.
                field_len = min(tab - cursor, STRLCPY_TEMP - 1)
                raw = text[cursor : cursor + field_len]
                cursor = tab + 1
                if field == 1:
                    block["lv_start"] = c_strtol10(raw)
                elif field == 2:
                    block["lv_end"] = c_strtol10(raw)
                elif field == 3:
                    block["percent"] = c_atof(raw)
                elif field == 4:
                    block["name"] = strlcpy(raw, ITEM_NAME_MAX_LEN + 1)
                elif field == 5:
                    block["count"] = c_strtol10(raw)

            # The lookup runs for every rank block of every line, including
            # blocks whose fields were never reached.
            resolved_by_name = items.by_original_name(block["name"])
            vnum = (
                resolved_by_name if resolved_by_name is not None else items.resolve(block["name"])
            )
            if vnum is None:
                raise DropCorpusError(f"{label}:{number}: no such item (name: {block['name']!r})")
            if resolved_by_name is None:
                stats["resolved_by_number"] += 1
            if not block["name"]:
                stats["empty_name_resolutions"] += 1
            if block["lv_start"] == 0:
                stats["skipped_level_start_zero"] += 1
                continue

            ranks[RANKS[index]].append(
                {
                    "level_start": block["lv_start"],
                    "level_end": block["lv_end"],
                    "percent": percent_to_10k_value(block["percent"]),
                    # Parsed by the original (``TDropItem::iCount``) and then
                    # ignored: ``CreateDropItem`` always creates one item.
                    "count": block["count"],
                    "vnum": vnum,
                    "name": decode_original_text(block["name"]),
                    "line": number,
                    # ``CreateDropItem`` selects a row with
                    # ``iLevelStart <= level <= iLevelEnd``.  A band that no
                    # reachable level satisfies is loaded by the original and
                    # never rolls; the catalog compiler drops it and reports
                    # the count instead of shipping a dead row.
                    "reachable": block["lv_start"] <= PLAYER_MAX_LEVEL
                    and block["lv_start"] <= block["lv_end"],
                }
            )
            if not ranks[RANKS[index]][-1]["reachable"]:
                stats["unreachable_rows"] += 1
                stats["unreachable_by_rank"][RANKS[index]] += 1
                unreachable_lines.add(number)
            elif block["lv_end"] > PLAYER_MAX_LEVEL:
                stats["clamped_level_end_rows"] += 1
            stats["rows_kept"] += 1

    for rank in RANKS:
        # ``std::sort`` with ``operator<`` on ``m_iLevelEnd`` only.
        ranks[rank].sort(key=lambda entry: entry["level_end"])
    stats["kept_by_rank"] = {rank: len(ranks[rank]) for rank in RANKS}
    stats["unreachable_lines"] = sorted(unreachable_lines)
    return ranks, stats


# ---------------------------------------------------------------------------
# ReadMonsterDropItemGroup
# ---------------------------------------------------------------------------


GROUP_TYPE_BYTES = tuple(kind.encode() for kind in GROUP_TYPES)


def _require_row_values(
    row: list[bytes], count: int, label: str, line: int, node: str, key: int, group: str
) -> None:
    """``pTok->at(n)`` aborts the process when the row is too short."""
    if len(row) < count:
        raise DropCorpusError(
            f"{label}:{line}: {node}: row {key} of a {group} group has {len(row)} value(s) "
            f"but the original reads {count}; at({len(row)}) would throw"
        )


def _new_group(kind: str, mob_vnum: int, name: str, line: int, **extra: int | None) -> dict:
    group = {"name": name, "line": line, "mob_vnum": mob_vnum, "type": kind, "items": []}
    group.update(extra)
    return group


def read_monster_drop_item_group(
    data: bytes, items: ItemTable, label: str
) -> tuple[dict[int, dict], dict[int, dict], dict[int, dict], dict[int, dict], dict]:
    """``ITEM_MANAGER::ReadMonsterDropItemGroup`` over the pinned table.

    Returns ``(drop, kill, limit, thiefgloves, stats)`` keyed by mob vnum.  A
    repeated ``drop`` group for one mob vnum *merges* into the group already in
    ``m_map_pkDropItemGroup`` (``bNew = false``); ``kill``/``limit``/
    ``thiefgloves`` insert into their own ``std::map``, so the first group for a
    mob vnum wins and any later one is discarded.
    """
    loader = TextFileLoader(data, label)
    maps: dict[str, dict[int, dict]] = {kind: {} for kind in GROUP_TYPES}
    stats: dict = {
        "groups": 0,
        "by_type": {kind: 0 for kind in GROUP_TYPES},
        "items": {kind: 0 for kind in GROUP_TYPES},
        "skipped_kill_drop_zero": 0,
        "merged_drop_groups": 0,
        "duplicates_dropped": {kind: 0 for kind in GROUP_TYPES},
        "first_gap_histogram": {},
        "distinct_names": 0,
    }
    names: set[bytes] = set()

    loader.set_top()
    for index in range(loader.child_count()):
        # ``GetCurrentNodeName`` is called *before* ``SetChildNode(i)`` while the
        # loader still sits on the parentless global node, so it returns false
        # and ``stName`` stays empty: the ``kr_`` prefix skip in the original is
        # dead code in this revision (and no pinned group name starts with it).
        # ``CMobItemGroup``/``CDropItemGroup`` also receive that empty name.
        loader.current_node_name()
        loader.set_child_node(index)
        node = loader.current
        node_name = decode_original_text(node.name)
        names.add(node.name)
        stats["groups"] += 1

        group_type = loader.token_string(b"type")
        if group_type is None:
            raise DropCorpusError(
                f"{label}:{node.line}: {node_name}: no type (kill|drop|limit|thiefgloves)"
            )
        if group_type not in GROUP_TYPE_BYTES:
            raise DropCorpusError(
                f"{label}:{node.line}: {node_name}: invalid type "
                f"{decode_original_text(group_type)!r} (kill|drop|limit|thiefgloves)"
            )
        kind = group_type.decode("ascii")

        mob_vnum = loader.token_integer(b"mob")
        if mob_vnum is None:
            raise DropCorpusError(f"{label}:{node.line}: {node_name}: no mob vnum")
        # ``iMobVnum`` is an ``int`` used as a ``DWORD`` map key.
        mob_vnum &= DWORD_MASK

        kill_drop = 1
        if kind == "kill":
            kill_drop = loader.token_integer(b"kill_drop")
            if kill_drop is None:
                raise DropCorpusError(f"{label}:{node.line}: {node_name}: no kill drop count")

        level_limit = None
        if kind == "limit":
            level_limit = loader.token_integer(b"level_limit")
            if level_limit is None:
                raise DropCorpusError(f"{label}:{node.line}: {node_name}: no level_limit")
            level_limit &= DWORD_MASK

        if kill_drop == 0:
            stats["skipped_kill_drop_zero"] += 1
            loader.set_parent_node()
            continue

        if kind == "drop":
            group = maps["drop"].get(mob_vnum)
            if group is None:
                group = _new_group(kind, mob_vnum, node_name, node.line)
                maps["drop"][mob_vnum] = group
            else:
                stats["merged_drop_groups"] += 1
        elif kind == "kill":
            group = _new_group(kind, mob_vnum, node_name, node.line, kill_drop=kill_drop)
        else:
            group = _new_group(kind, mob_vnum, node_name, node.line, level_limit=level_limit)

        first_gap = ROW_KEY_LIMIT + 1
        for key in range(1, ROW_KEY_LIMIT + 1):
            row = loader.token(str(key).encode("ascii"))
            if row is None:
                first_gap = key
                break
            if not row:
                raise DropCorpusError(
                    f"{label}:{node.line}: {node_name}: row {key} has no values; "
                    "the original's at(0) would throw"
                )
            line = node.lines.get(str(key).encode("ascii"), node.line)
            name = row[0]
            vnum = items.resolve(name)
            if vnum is None:
                raise DropCorpusError(
                    f"{label}:{line}: {node_name}: no such item {decode_original_text(name)!r}"
                )
            item = {"vnum": vnum, "name": decode_original_text(name), "line": line}

            if kind == "kill":
                _require_row_values(row, 4, label, line, node_name, key, kind)
                item["count"] = c_strtol10(row[1])
                if item["count"] < 1:
                    raise DropCorpusError(
                        f"{label}:{line}: {node_name}: no count for item "
                        f"{decode_original_text(name)!r}"
                    )
                # ``iPartPct`` is a raw integer percentage on top of the group's
                # cumulative vector; zero aborts the load.
                part_pct = c_strtol10(row[2])
                if part_pct == 0:
                    raise DropCorpusError(
                        f"{label}:{line}: {node_name}: no drop percent for item "
                        f"{decode_original_text(name)!r}"
                    )
                item["part_pct"] = part_pct
                item["cumulative_pct"] = part_pct + (
                    group["items"][-1]["cumulative_pct"] if group["items"] else 0
                )
                item["rare_pct"] = min(max(c_strtol10(row[3]), 0), 100)
            else:
                _require_row_values(row, 3, label, line, node_name, key, kind)
                item["count"] = c_strtol10(row[1])
                if item["count"] < 1:
                    raise DropCorpusError(
                        f"{label}:{line}: {node_name}: no count for item "
                        f"{decode_original_text(name)!r}"
                    )
                item["pct_10k"] = percent_to_10k_value(c_atof(row[2]))

            group["items"].append(item)
            stats["items"][kind] += 1

        stats["by_type"][kind] += 1
        stats["first_gap_histogram"][str(first_gap)] = (
            stats["first_gap_histogram"].get(str(first_gap), 0) + 1
        )

        if kind == "drop":
            # ``drop`` groups already live in the map, and a merge appends.
            pass
        elif mob_vnum in maps[kind]:
            stats["duplicates_dropped"][kind] += 1
        else:
            maps[kind][mob_vnum] = group

        loader.set_parent_node()

    stats["distinct_names"] = len(names)
    return maps["drop"], maps["kill"], maps["limit"], maps["thiefgloves"], stats


# ---------------------------------------------------------------------------
# corpus assembly
# ---------------------------------------------------------------------------


def source_revision(source_root: Path) -> str | None:
    """Pinned checkout revision, when the ignored snapshot still has its ``.git``."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    revision = completed.stdout.strip()
    if completed.returncode != 0 or len(revision) != 40:
        return None
    return revision if all(char in "0123456789abcdef" for char in revision) else None


def corpus_hash(corpus: dict) -> str:
    """Digest of every field except ``content_hash`` itself."""
    payload = {key: value for key, value in corpus.items() if key != "content_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def compile_corpus(source_root: Path) -> dict:
    """Compile the three pinned tables into the deterministic drop corpus."""
    inputs = {
        "common_drop_item": COMMON_DROP,
        "mob_drop_item": MOB_DROP,
        "item_proto": ITEM_PROTO,
    }
    payloads: dict[str, bytes] = {}
    for label, relative in inputs.items():
        path = source_root / relative
        if not path.is_file():
            raise DropCorpusError(f"missing pinned source file: {path}")
        payloads[label] = path.read_bytes()

    items = load_item_table(payloads["item_proto"])
    common, common_stats = parse_common_drop(payloads["common_drop_item"], items, str(COMMON_DROP))
    drop, kill, limit, gloves, group_stats = read_monster_drop_item_group(
        payloads["mob_drop_item"], items, str(MOB_DROP)
    )
    by_type = {"drop": drop, "kill": kill, "limit": limit, "thiefgloves": gloves}
    corpus = {
        "schema": SCHEMA,
        "schema_version": VERSION,
        "source": {
            "root": str(source_root),
            "revision": source_revision(source_root),
            "files": {
                label: {
                    "path": str(relative),
                    "bytes": len(payloads[label]),
                    "sha256": hashlib.sha256(payloads[label]).hexdigest(),
                }
                for label, relative in inputs.items()
            },
        },
        "ranks": list(RANKS),
        "item_prototypes": {
            "count": len(items),
            "range_rows": len(items.range_rows),
            "sha256": items.identity(),
        },
        "common": common,
        "common_stats": common_stats,
        "groups": {
            kind: {str(vnum): rows[vnum] for vnum in sorted(rows)} for kind, rows in by_type.items()
        },
        "group_stats": group_stats,
    }
    corpus["summary"] = {
        "common_rows": common_stats["rows_kept"],
        "groups": group_stats["groups"],
        "groups_by_type": {kind: len(corpus["groups"][kind]) for kind in GROUP_TYPES},
        "group_rows": sum(group_stats["items"].values()),
        "mobs_with_groups": len(
            {int(vnum) for kind in GROUP_TYPES for vnum in corpus["groups"][kind]}
        ),
    }
    corpus["content_hash"] = corpus_hash(corpus)
    return corpus


def corpus_summary(corpus: dict) -> str:
    source = corpus["source"]
    prototypes = corpus["item_prototypes"]
    common = corpus["common_stats"]
    groups = corpus["group_stats"]
    summary = corpus["summary"]
    lines = [
        f"{corpus['schema']} v{corpus['schema_version']} ({corpus['content_hash'][:16]})",
        f"source: {source['root']} @ {source['revision'] or 'unknown revision'}",
    ]
    for label in sorted(source["files"]):
        info = source["files"][label]
        lines.append(
            f"  {label}: {info['path']} {info['bytes']} bytes sha256 {info['sha256'][:16]}"
        )
    lines.append(
        f"item prototypes: {prototypes['count']} rows "
        f"({prototypes['range_rows']} with a vnum range) sha256 {prototypes['sha256'][:16]}"
    )
    lines.append(
        f"common drops: {common['rows_kept']} rows kept of {common['lines']} lines "
        f"(lv_start==0 skipped {common['skipped_level_start_zero']}, "
        f"resolved by number {common['resolved_by_number']}, "
        f"empty-name resolutions {common['empty_name_resolutions']})"
    )
    lines.append(
        f"  unreachable at level cap {common['max_player_level']}: "
        f"{common['unreachable_rows']} row(s) on {len(common['unreachable_lines'])} "
        f"pinned line(s) {common['unreachable_lines'][:3]}"
        f"{'...' if len(common['unreachable_lines']) > 3 else ''}, "
        f"clamped level_end {common['clamped_level_end_rows']}"
    )
    for rank in RANKS:
        lines.append(f"  {rank}: {common['kept_by_rank'][rank]}")
    zero = groups["skipped_kill_drop_zero"]
    installed = sum(groups["by_type"].values())
    lines.append(
        f"monster groups: {groups['groups']} nodes, {installed} installed "
        f"({zero} kill node(s) skipped by kill_drop==0), "
        f"{groups['distinct_names']} distinct names, {summary['group_rows']} rows"
    )
    for kind in GROUP_TYPES:
        lines.append(
            f"  {kind}: {groups['by_type'][kind]} installed nodes / "
            f"{len(corpus['groups'][kind])} mob vnums / "
            f"{groups['items'][kind]} rows / "
            f"{groups['duplicates_dropped'][kind]} duplicate group(s) dropped"
        )
    lines.append(f"  merged drop groups {groups['merged_drop_groups']}")
    lines.append(f"  first row-probe gap: {groups['first_gap_histogram']}")
    return "\n".join(lines)


def corpus_command(args: argparse.Namespace) -> int:
    corpus = compile_corpus(args.source.resolve())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(corpus, indent=1, sort_keys=True) + "\n")
        print(f"wrote {args.output}")
    if args.summary or not args.output:
        print(corpus_summary(corpus))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Pinned git.old-metin2.com server checkout",
    )
    parser.add_argument("--summary", action="store_true", help="Print the compiled corpus summary")
    parser.add_argument("--output", type=Path, help="Write the corpus JSON here")
    args = parser.parse_args()
    return corpus_command(args)


if __name__ == "__main__":
    raise SystemExit(main())
