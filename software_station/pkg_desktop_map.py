#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional: map installed pkg → one of its .desktop files.

This version uses:
  - 'pkg query %n'           to enumerate installed package names
  - 'pkg info -l <pkgname>'  to list files installed by each package

All subprocess calls capture stdout and suppress stderr to avoid noisy logs.

API
- build_pkg_map_async()
- desktop_for_pkg(pkgname) -> str | None
"""
from __future__ import annotations

import subprocess
import threading
from typing import Optional, Dict

_pkg_map: Dict[str, str] = {}
_ready = threading.Event()

def _run(cmd: list[str]) -> str:
    """Run a command, return stdout as text; swallow errors and stderr."""
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return cp.stdout or ""
    except Exception:
        return ""

def build_pkg_map_async():
    """Build the pkg→desktop map in a background thread."""
    def work():
        try:
            # All installed package names, one per line
            pkgs_txt = _run(["pkg", "query", "%n"])
            if not pkgs_txt:
                return
            for p in pkgs_txt.splitlines():
                if not p:
                    continue
                # List files for this package
                listing = _run(["pkg", "info", "-l", p])
                if not listing:
                    continue
                # Lines typically look like: "\t/usr/local/share/applications/foo.desktop"
                for line in listing.splitlines():
                    path = line.strip()
                    if not path or not path.endswith(".desktop"):
                        continue
                    _pkg_map[p] = path
                    break  # one .desktop is enough to map this package
        finally:
            _ready.set()
    threading.Thread(target=work, daemon=True).start()

def desktop_for_pkg(pkg: str) -> Optional[str]:
    """Return a known .desktop path for the package, if any."""
    return _pkg_map.get(pkg)

