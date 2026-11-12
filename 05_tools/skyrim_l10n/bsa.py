"""Read-only reader for Bethesda BSA archives (TES5 v104 and SSE v105).

Only reading/extracting is supported. Packaging is left to BSArch or loose files.

Usage:
    python -I bsa.py list <archive.bsa> [--filter REGEX]
    python -I bsa.py extract <archive.bsa> <out_dir> [--filter REGEX]
"""
import argparse
import os
import re
import struct
import zlib

FLAG_DIR_NAMES = 0x1
FLAG_FILE_NAMES = 0x2
FLAG_COMPRESSED = 0x4
FLAG_EMBED_NAMES = 0x100
SIZE_COMPRESS_TOGGLE = 0x40000000
SIZE_MASK = 0x3FFFFFFF


class BsaEntry:
    __slots__ = ("path", "raw_size", "offset")

    def __init__(self, path, raw_size, offset):
        self.path = path  # lowercase, forward slashes, e.g. "strings/skyrim_english.strings"
        self.raw_size = raw_size
        self.offset = offset

    @property
    def stored_size(self):
        return self.raw_size & SIZE_MASK


class BsaArchive:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            header = f.read(36)
            (magic, self.version, _offset, self.flags, folder_count, file_count,
             _folder_names_len, file_names_len, self.file_flags, _pad) = struct.unpack("<4sIIIIIIIHH", header)
            if magic != b"BSA\0":
                raise ValueError(f"{path}: not a BSA archive")
            if self.version not in (104, 105):
                raise ValueError(f"{path}: unsupported BSA version {self.version}")
            if not (self.flags & FLAG_DIR_NAMES and self.flags & FLAG_FILE_NAMES):
                raise ValueError(f"{path}: archives without embedded name tables are not supported")
            record_size = 24 if self.version == 105 else 16
            counts = []
            for _ in range(folder_count):
                rec = f.read(record_size)
                counts.append(struct.unpack_from("<QI", rec)[1])
            pending = []
            for count in counts:
                name_len = f.read(1)[0]
                folder = f.read(name_len)[:-1].decode("cp1252")
                for _ in range(count):
                    _hash, size, off = struct.unpack("<QII", f.read(16))
                    pending.append((folder, size, off))
            names = f.read(file_names_len).split(b"\0")
        if len(names) - 1 != file_count or len(pending) != file_count:
            raise ValueError(f"{path}: name table mismatch ({len(names) - 1} names, {file_count} files)")
        self.entries = {}
        for (folder, size, off), name in zip(pending, names):
            full = (folder + "\\" + name.decode("cp1252")).replace("\\", "/").lower()
            self.entries[full] = BsaEntry(full, size, off)

    def is_compressed(self, entry):
        default = bool(self.flags & FLAG_COMPRESSED)
        return default != bool(entry.raw_size & SIZE_COMPRESS_TOGGLE)

    def read(self, path):
        entry = self.entries[path.replace("\\", "/").lower()]
        with open(self.path, "rb") as f:
            f.seek(entry.offset)
            size = entry.stored_size
            if self.flags & FLAG_EMBED_NAMES:
                name_len = f.read(1)[0]
                f.read(name_len)
                size -= name_len + 1
            data = f.read(size)
        if not self.is_compressed(entry):
            return data
        original_size = struct.unpack_from("<I", data)[0]
        payload = data[4:]
        if self.version == 104:
            out = zlib.decompress(payload)
        else:
            try:
                import lz4.frame  # optional dependency, only needed for compressed SSE archives
            except ImportError as exc:
                raise RuntimeError("compressed SSE entry requires the 'lz4' package") from exc
            out = lz4.frame.decompress(payload)
        if len(out) != original_size:
            raise ValueError(f"{path}: decompressed size {len(out)} != {original_size}")
        return out

    def list(self, pattern=None):
        rx = re.compile(pattern, re.I) if pattern else None
        return sorted(p for p in self.entries if rx is None or rx.search(p))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("archive")
    p_list.add_argument("--filter")
    p_ext = sub.add_parser("extract")
    p_ext.add_argument("archive")
    p_ext.add_argument("out_dir")
    p_ext.add_argument("--filter")
    args = ap.parse_args()

    bsa = BsaArchive(args.archive)
    if args.cmd == "list":
        for p in bsa.list(args.filter):
            e = bsa.entries[p]
            print(f"{e.stored_size:>12}  {'C' if bsa.is_compressed(e) else '-'}  {p}")
    else:
        for p in bsa.list(args.filter):
            dest = os.path.join(args.out_dir, *p.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(bsa.read(p))
            print(f"extracted {p}")


if __name__ == "__main__":
    main()
