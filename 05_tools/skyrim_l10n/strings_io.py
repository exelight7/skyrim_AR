"""Reader/writer for Bethesda localized string tables (.strings/.dlstrings/.ilstrings).

Layout:
    u32 count, u32 data_size,
    count * (u32 string_id, u32 offset),
    data blob.
.strings entries are NUL-terminated. .dlstrings/.ilstrings entries are
u32 length (including the NUL) followed by the bytes and a NUL.

Text is stored as raw bytes; Skyrim SE files are UTF-8 (verified on 1.7.104 data).

Usage:
    python -I strings_io.py info <file>
    python -I strings_io.py roundtrip <file>      # rebuild and compare byte-for-byte
"""
import argparse
import hashlib
import os
import struct
import sys


def kind_of(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext not in ("strings", "dlstrings", "ilstrings"):
        raise ValueError(f"unknown string table extension: {path}")
    return ext


class StringTable:
    """Ordered string table. `directory` keeps the original (id, offset) order."""

    def __init__(self, kind):
        self.kind = kind
        self.directory = []   # list of (string_id, offset) in file order
        self.values = {}      # offset -> bytes (without terminator)

    # ---------- reading ----------
    @classmethod
    def parse(cls, data, kind):
        table = cls(kind)
        if len(data) < 8:
            raise ValueError("truncated header")
        count, data_size = struct.unpack_from("<II", data, 0)
        base = 8 + 8 * count
        if base + data_size != len(data):
            raise ValueError(f"size mismatch: header says {base + data_size}, file is {len(data)}")
        for i in range(count):
            sid, off = struct.unpack_from("<II", data, 8 + 8 * i)
            table.directory.append((sid, off))
            if off not in table.values:
                table.values[off] = cls._read_value(data, base + off, kind)
        return table

    @staticmethod
    def _read_value(data, pos, kind):
        if kind == "strings":
            end = data.index(b"\0", pos)
            return data[pos:end]
        length = struct.unpack_from("<I", data, pos)[0]
        raw = data[pos + 4:pos + 4 + length]
        if length == 0 or raw[-1:] != b"\0":
            raise ValueError(f"bad length-prefixed entry at {pos}")
        return raw[:-1]

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls.parse(f.read(), kind_of(path))

    def items(self):
        """Yield (string_id, bytes) in directory order."""
        for sid, off in self.directory:
            yield sid, self.values[off]

    def as_dict(self):
        return {sid: val for sid, val in self.items()}

    # ---------- writing ----------
    def _encode_value(self, value):
        if b"\0" in value:
            raise ValueError("embedded NUL in string value")
        if self.kind == "strings":
            return value + b"\0"
        return struct.pack("<I", len(value) + 1) + value + b"\0"

    def serialize_preserving_layout(self):
        """Rebuild using the original offsets order (used to prove a byte-identical roundtrip)."""
        blob = bytearray()
        new_offsets = {}
        for off in sorted(self.values):
            new_offsets[off] = len(blob)
            blob += self._encode_value(self.values[off])
        return self._pack([(sid, new_offsets[off]) for sid, off in self.directory], bytes(blob))

    @classmethod
    def build(cls, kind, entries, dedupe=True):
        """Build a new table from (string_id, bytes) pairs, keeping the given order."""
        table = cls(kind)
        blob = bytearray()
        seen = {}
        directory = []
        for sid, value in entries:
            if dedupe and value in seen:
                directory.append((sid, seen[value]))
                continue
            off = len(blob)
            blob += table._encode_value(value)
            seen[value] = off
            directory.append((sid, off))
        return table._pack(directory, bytes(blob))

    @staticmethod
    def _pack(directory, blob):
        out = bytearray(struct.pack("<II", len(directory), len(blob)))
        for sid, off in directory:
            out += struct.pack("<II", sid, off)
        return bytes(out + blob)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def roundtrip_check(path):
    with open(path, "rb") as f:
        original = f.read()
    table = StringTable.parse(original, kind_of(path))
    rebuilt = table.serialize_preserving_layout()
    return {
        "file": os.path.basename(path),
        "entries": len(table.directory),
        "unique_offsets": len(table.values),
        "sha256_original": sha256(original),
        "sha256_rebuilt": sha256(rebuilt),
        "identical": original == rebuilt,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["info", "roundtrip"])
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    failed = 0
    for path in args.files:
        if args.cmd == "info":
            t = StringTable.load(path)
            print(f"{path}: {len(t.directory)} entries, {len(t.values)} unique offsets")
        else:
            r = roundtrip_check(path)
            failed += not r["identical"]
            print(f"{'OK  ' if r['identical'] else 'FAIL'} {r['file']} entries={r['entries']} sha256={r['sha256_original'][:16]}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
