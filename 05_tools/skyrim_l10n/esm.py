"""Read-only streaming parser for Skyrim SE plugins (ESM/ESP/ESL, record version 44).

Only what the localization pipeline needs: record headers, group nesting, zlib-compressed
record bodies and subrecords (including XXXX large-size subrecords).

Usage:
    python -I esm.py stats <plugin>          # record counts per type
"""
import argparse
import collections
import mmap
import struct
import zlib

FLAG_COMPRESSED = 0x00040000
FLAG_LOCALIZED = 0x00000080

# Record types without any player-visible text; their bodies are never decompressed.
# TREE/MSTT/STAT are decoded because harvestable plants (TREE) and moveable statics carry FULL names.
SKIP_BODY = {b"LAND", b"NAVM", b"NAVI", b"PGRD", b"PHZD", b"PGRE", b"PMIS", b"PARW", b"PBAR", b"PBEA",
             b"PCON", b"PFLA", b"IDLE", b"ANIO", b"TXST", b"GRAS",
             b"ADDN", b"LGTM", b"IMGS", b"IMAD", b"SNDR", b"SOUN", b"SOPM", b"ASPC", b"MUST",
             b"MUSC", b"CAMS", b"CPTH", b"DUAL", b"MATO", b"MATT", b"ARTO", b"DEBR", b"RFCT",
             b"LCRT", b"LTEX", b"AACT", b"FSTP", b"FSTS", b"VTYP", b"DLBR", b"DLVW", b"OTFT"}


class Record:
    __slots__ = ("type", "flags", "form_id", "data", "parents")

    def __init__(self, rtype, flags, form_id, data, parents):
        self.type = rtype          # str, e.g. "INFO"
        self.flags = flags
        self.form_id = form_id     # raw in-file FormID (top byte = master index)
        self.data = data           # decompressed body (bytes) or None if skipped
        self.parents = parents     # tuple of (group_type, label_int) from outermost to innermost

    def subrecords(self):
        """Yield (type, payload) pairs."""
        data, pos, n = self.data, 0, len(self.data)
        big = None
        while pos + 6 <= n:
            sub = data[pos:pos + 4]
            size = struct.unpack_from("<H", data, pos + 4)[0]
            pos += 6
            if sub == b"XXXX":
                big = struct.unpack_from("<I", data, pos)[0]
                pos += size
                continue
            if big is not None:
                size, big = big, None
            yield sub.decode("ascii"), data[pos:pos + size]
            pos += size


class Plugin:
    def __init__(self, path):
        self.path = path
        self._f = open(path, "rb")
        self.buf = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        rtype, size, flags = struct.unpack_from("<4sII", self.buf, 0)
        if rtype != b"TES4":
            raise ValueError(f"{path}: not a TES4 plugin")
        self.header_flags = flags
        header = Record("TES4", flags, 0, bytes(self.buf[24:24 + size]), ())
        self.masters = [p[:-1].decode("cp1252") for t, p in header.subrecords() if t == "MAST"]
        self._first_group = 24 + size

    @property
    def localized(self):
        return bool(self.header_flags & FLAG_LOCALIZED)

    def close(self):
        self.buf.close()
        self._f.close()

    def records(self, want=None):
        """Yield every record in file order. `want`: optional set of record type strings to decode."""
        stack = []        # list of (end_offset, group_type, label)
        buf = self.buf
        pos, end = self._first_group, len(buf)
        while pos < end:
            while stack and pos >= stack[-1][0]:
                stack.pop()
            rtype = bytes(buf[pos:pos + 4])
            if rtype == b"GRUP":
                gsize, label, gtype = struct.unpack_from("<IIi", buf, pos + 4)
                stack.append((pos + gsize, gtype, label))
                pos += 24
                continue
            dsize, flags, form_id = struct.unpack_from("<III", buf, pos + 4)
            body_start = pos + 24
            pos = body_start + dsize
            name = rtype.decode("ascii")
            if rtype in SKIP_BODY or (want is not None and name not in want):
                continue
            raw = buf[body_start:body_start + dsize]
            if flags & FLAG_COMPRESSED:
                expected = struct.unpack_from("<I", raw, 0)[0]
                data = zlib.decompress(raw[4:])
                if len(data) != expected:
                    raise ValueError(f"{self.path}: {name} {form_id:08X} bad decompressed size")
            else:
                data = bytes(raw)
            yield Record(name, flags, form_id, data, tuple((g, l) for _e, g, l in stack))

    def form_key(self, raw_form_id, plugin_name):
        """Resolve an in-file FormID to a global key 'Plugin.esm:XXXXXX'."""
        if raw_form_id == 0:
            return None
        idx = raw_form_id >> 24
        owner = self.masters[idx] if idx < len(self.masters) else plugin_name
        return f"{owner}:{raw_form_id & 0xFFFFFF:06X}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["stats"])
    ap.add_argument("plugin")
    args = ap.parse_args()
    p = Plugin(args.plugin)
    counts = collections.Counter(r.type for r in p.records())
    print(f"masters={p.masters} localized={p.localized}")
    for t, c in counts.most_common():
        print(f"{t} {c}")


if __name__ == "__main__":
    main()
