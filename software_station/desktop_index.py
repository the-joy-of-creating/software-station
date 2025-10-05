#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop entry index for quick lookups (localized names + icons).

API
- build_index_async()
- wait_until_ready(timeout=2.0)  # optional
- best_guess(token) -> dict | None
"""
from __future__ import annotations

import os
import threading
import logging
from glob import glob
from functools import lru_cache
from typing import Optional, Dict

from gi.repository import GLib

logger = logging.getLogger(__name__)

_DESKTOP_DIRS = (
    "/usr/local/share/applications",
    "/usr/share/applications",
    os.path.expanduser("~/.local/share/applications"),
)

_index: Dict[str, Dict[str, str]] = {}
_ready = threading.Event()

def _parse_localized_name(kf: GLib.KeyFile, locale: str) -> Optional[str]:
    sect = "Desktop Entry"
    try:
        probes = []
        if locale:
            probes.append(locale)
            if "." in locale:
                probes.append(locale.split(".", 1)[0])  # en_US
            if "_" in locale:
                probes.append(locale.split("_", 1)[0])  # en
        for p in probes:
            key = f"Name[{p}]"
            if kf.has_key(sect, key):
                return kf.get_string(sect, key)
        if kf.has_key(sect, "Name"):
            return kf.get_string(sect, "Name")
    except Exception:
        pass
    return None

def build_index_async():
    def work():
        try:
            locale = os.environ.get("LC_ALL") or os.environ.get("LANG") or "en_US"
            for base in _DESKTOP_DIRS:
                if not os.path.isdir(base):
                    logger.debug(f"Desktop directory not found: {base}")
                    continue
                    
                for path in glob(os.path.join(base, "*.desktop")):
                    try:
                        kf = GLib.KeyFile()
                        kf.load_from_file(path, GLib.KeyFileFlags.NONE)
                        if not kf.has_group("Desktop Entry"):
                            continue
                        name = _parse_localized_name(kf, locale)
                        icon = kf.get_string("Desktop Entry", "Icon") if kf.has_key("Desktop Entry", "Icon") else None
                        execv = kf.get_string("Desktop Entry", "Exec") if kf.has_key("Desktop Entry", "Exec") else ""
                        tryexec = kf.get_string("Desktop Entry", "TryExec") if kf.has_key("Desktop Entry", "TryExec") else ""
                        did = os.path.basename(path)  # e.g., firefox.desktop

                        tokens = {did}
                        if execv:
                            tokens.add(execv.split()[0])
                        if tryexec:
                            tokens.add(os.path.basename(tryexec))
                        for t in tokens:
                            _index[t] = {"name": name, "icon": icon, "desktop_id": did}
                    except Exception as e:
                        logger.debug(f"Failed to process desktop file '{path}': {e}")
                        continue
        except Exception as e:
            logger.error(f"Error during desktop index building: {e}", exc_info=True)
        finally:
            _ready.set()
    threading.Thread(target=work, daemon=True).start()

def wait_until_ready(timeout: float = 2.0) -> bool:
    return _ready.wait(timeout)

@lru_cache(maxsize=4096)
def best_guess(token: str) -> Optional[Dict[str, str]]:
    return _index.get(token)
