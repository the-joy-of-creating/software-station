#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from typing import Optional, Callable

# -------------------------
# Optional legacy fallback
# -------------------------
# If your repository ships embedded XPM icons, keep using them as a last resort.
_legacy_get_pixbuf = None
try:
    # If your legacy module exposes a "get_pixbuf(name, size)" or similar,
    # adapt it here. If not, this will remain None and simply not be used.
    import software_station_xpm as _xpm

    # Try a few common names; bind the first that exists.
    if hasattr(_xpm, "get_pixbuf") and callable(_xpm.get_pixbuf):
        _legacy_get_pixbuf = _xpm.get_pixbuf  # type: ignore
    elif hasattr(_xpm, "icon_pixbuf") and callable(_xpm.icon_pixbuf):
        _legacy_get_pixbuf = _xpm.icon_pixbuf  # type: ignore
    # Else: leave as None; we'll skip legacy fallback.
except Exception:
    _xpm = None  # not fatal

# --------------------------------------
# Themed, thread-safe enhanced helpers
# --------------------------------------
_THEMED_ICONS_AVAILABLE = False
try:
    from gi.repository import Gtk, GdkPixbuf  # noqa: F401

    # Our improved, thread-safe, theme-aware implementation lives here:
    from software_station.icons import (
        init_icon_runtime as _init_icon_runtime,
        resolve_label_and_icon_async as _resolve_label_and_icon_async,
        resolve_label_and_icon_sync as _resolve_label_and_icon_sync,
    )
    from software_station.accessories_map import ACCESSORIES_MAP as _ACCESSORIES_MAP

    _THEMED_ICONS_AVAILABLE = True
except Exception:
    # PyGObject or the helper modules not available - themed path disabled.
    _ACCESSORIES_MAP = {}  # type: ignore


def init_icons_runtime() -> None:
    """
    Initialize the themed icon runtime (must be called on the GTK main thread).
    Safe to call even if themed icons are unavailable (becomes a no-op).
    """
    if _THEMED_ICONS_AVAILABLE:
        _init_icon_runtime()  # type: ignore[misc]


def _category_uses_themed(category: str) -> bool:
    # Use the themed path for all categories
    return True


def themed_icon_and_label_async(
    category: str,
    pkg_name: str,
    size: int,
    on_ready: Callable[[str, Optional["GdkPixbuf.Pixbuf"]], None],
) -> None:
    """
    Resolve a label + icon without blocking the UI.
    - If themed stack is available and enabled for the category, use it.
    - Otherwise, offload legacy_get_pixbuf to a worker thread.
    The callback runs on the GTK main thread.
    """
    if _THEMED_ICONS_AVAILABLE and _category_uses_themed(category):
        _resolve_label_and_icon_async(pkg_name, _ACCESSORIES_MAP, size, on_ready)  # type: ignore[misc]
        return

    # Non-themed path: offload legacy_get_pixbuf to a worker thread
    def worker():
        pix = None
        if _legacy_get_pixbuf:
            try:
                pix = _legacy_get_pixbuf(pkg_name, size)  # type: ignore[call-arg]
            except Exception:
                pix = None
        # Call back on main thread
        from gi.repository import GLib
        GLib.idle_add(on_ready, pkg_name, pix)
    
    import threading
    threading.Thread(target=worker, daemon=True).start()


def themed_icon_and_label_sync(
    category: str,
    pkg_name: str,
    size: int = 32,
):
    """
    Resolve label + icon synchronously (must run on the GTK main thread).
    """
    if _THEMED_ICONS_AVAILABLE and _category_uses_themed(category):
        # returns (label, pixbuf)
        return _resolve_label_and_icon_sync(pkg_name, _ACCESSORIES_MAP, size=size)  # type: ignore[misc]

    # Legacy path: label = pkg name; icon via XPM if available.
    pix = None
    if _legacy_get_pixbuf:
        try:
            pix = _legacy_get_pixbuf(pkg_name, size)  # type: ignore[call-arg]
        except Exception:
            pix = None
    return pkg_name, pix


# -------------------------------------------------------
# Optional convenience for existing callers (compat)
# -------------------------------------------------------
def get_icon_for_package(pkg_name: str, size: int = 32):
    """
    Backward-compatible helper for callers that only want an icon pixbuf
    for a package name. Attempts themed resolution first (if available
    and category policy allows), then falls back to XPM, then None.
    """
    # Use themed sync path under 'Accessories' policy; otherwise legacy only.
    if _THEMED_ICONS_AVAILABLE and _category_uses_themed("Accessories"):
        # Only care about the pixbuf; ignore the label.
        try:
            _, pix = _resolve_label_and_icon_sync(pkg_name, _ACCESSORIES_MAP, size=size)  # type: ignore[misc]
            if pix is not None:
                return pix
        except Exception:
            pass

    if _legacy_get_pixbuf:
        try:
            return _legacy_get_pixbuf(pkg_name, size)  # type: ignore[call-arg]
        except Exception:
            return None
    return None


def get_friendly_label(pkg_name: str) -> str:
    """
    Best-effort friendly label for a package (falls back to pkg_name).
    The themed path provides localized names via desktop index; otherwise
    we just return the package name.
    """
    if _THEMED_ICONS_AVAILABLE and _category_uses_themed("Accessories"):
        try:
            label, _ = _resolve_label_and_icon_sync(pkg_name, _ACCESSORIES_MAP, size=16)  # type: ignore[misc]
            return label or pkg_name
        except Exception:
            return pkg_name
    return pkg_name


__all__ = [
    # New themed API
    "init_icons_runtime",
    "themed_icon_and_label_async",
    "themed_icon_and_label_sync",
    # Optional compatibility helpers
    "get_icon_for_package",
    "get_friendly_label",
]
