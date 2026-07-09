#!/usr/bin/env python3
"""
Extract the name and version from a XAR-format .pkg file.

Prints two lines to stdout:
  <name>
  <version>

Name resolution order (first non-empty value wins):
  Distribution: <title> element
  Distribution: <pkg-ref> CFBundleName attribute
  PackageInfo:  identifier attribute (last component after the final dot)
  PackageInfo:  <bundle> CFBundleName attribute

Version resolution order:
  PackageInfo:  version attribute
  Distribution: <pkg-ref> version attribute (only if single component)

If name or version cannot be determined the script prints an empty string for
that line. The caller is responsible for falling back to the original filename.

Note: This script is designed for single-component .pkg files. Multi-component
installers (those with multiple <pkg-ref> entries carrying different versions)
are unsupported — version will be left empty so the caller can fall back to
the original supplied filename rather than picking the wrong component version.
"""
import os, struct, zlib, xml.etree.ElementTree as ET, sys


def _read_heap_entry(f, toc_entry, heap_start):
    d = toc_entry.find('data')
    if d is None:
        return None
    try:
        offset = int(d.find('offset').text)
        length = int(d.find('length').text)
        f.seek(heap_start + offset)
        raw = f.read(length)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        return ET.fromstring(raw)
    except Exception:
        return None


def get_pkg_info(path):
    name = None
    version = None

    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'xar!':
                return None, None
            header_size = struct.unpack('>H', f.read(2))[0]
            f.read(2)
            toc_len = struct.unpack('>Q', f.read(8))[0]
            f.read(12)
            f.seek(header_size)
            toc = ET.fromstring(zlib.decompress(f.read(toc_len)))
            heap_start = header_size + toc_len

            for fe in toc.iter('file'):
                n = fe.find('name')
                if n is None:
                    continue

                if n.text == 'Distribution':
                    root = _read_heap_entry(f, fe, heap_start)
                    if root is None:
                        continue
                    # Title
                    if not name:
                        t = root.find('title')
                        if t is not None and t.text and t.text.strip():
                            name = t.text.strip()
                    # CFBundleName from pkg-ref as fallback name
                    if not name:
                        for ref in root.iter('pkg-ref'):
                            n_attr = ref.get('CFBundleName')
                            if n_attr:
                                name = n_attr
                                break
                    # Version from pkg-ref — only trust if single component
                    if not version:
                        refs_with_version = [
                            ref.get('version')
                            for ref in root.iter('pkg-ref')
                            if ref.get('version')
                        ]
                        unique_versions = set(refs_with_version)
                        if len(unique_versions) == 1:
                            version = refs_with_version[0]
                        # Multiple distinct versions = multi-component pkg; leave version None

                elif n.text == 'PackageInfo':
                    root = _read_heap_entry(f, fe, heap_start)
                    if root is None:
                        continue
                    # Version from PackageInfo attribute (most reliable)
                    if not version:
                        v = root.get('version')
                        if v:
                            version = v
                    # Name from identifier (e.g. com.sentinelone.pkg → sentinelone)
                    if not name:
                        ident = root.get('identifier', '')
                        if ident:
                            name = ident.split('.')[-1]
                    # CFBundleName from nested bundle element
                    if not name:
                        for b in root.iter('bundle'):
                            n_attr = b.get('CFBundleName')
                            if n_attr:
                                name = n_attr
                                break

    except Exception:
        return None, None

    return name, version


if __name__ == '__main__':
    path = sys.argv[1]
    pkg_name, pkg_version = get_pkg_info(path)

    # Fall back to original filename (without .pkg extension) if name not found
    if not pkg_name:
        pkg_name = os.path.splitext(os.path.basename(path))[0]

    print(pkg_name.replace(' ', '-'))
    print(pkg_version or '')
