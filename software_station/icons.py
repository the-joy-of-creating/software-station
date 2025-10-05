#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Optional, Tuple, Callable, Dict

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

# Optional helpers (safe to miss)
try:
    from . import desktop_index
except Exception:
    desktop_index = None  # type: ignore
try:
    from . import pkg_desktop_map
except Exception:
    pkg_desktop_map = None  # type: ignore

ICON_FALLBACK = "package-x-generic"

# --- GTK objects must only be touched on the main thread ---
_icon_theme: Gtk.IconTheme | None = None
_scale: int = 1

# Main-thread-only pixbuf cache: key = (icon_name or fallback, size, scale)
_pixbuf_cache: Dict[tuple[str, int, int], Optional[GdkPixbuf.Pixbuf]] = {}

# Small worker pool: enough parallelism without hammering disks
from concurrent.futures import ThreadPoolExecutor
_executor = ThreadPoolExecutor(max_workers=3)

def _assert_main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("GTK must be accessed on the main thread")

def _compute_scale_factor() -> int:
    display = Gdk.Display.get_default()
    if not display:
        return 1
    try:
        mon = display.get_primary_monitor()
        return mon.get_scale_factor() if mon else 1
    except Exception:
        return 1

def _rebuild_scale_and_clear_cache(*_args):
    global _scale
    _scale = _compute_scale_factor()
    _pixbuf_cache.clear()

def _on_icon_theme_change(*_args):
    _pixbuf_cache.clear()

def init_icon_runtime():
    """
    Call ONCE at app startup (main thread).
    - creates global IconTheme
    - wires watchers for theme & DPI changes
    - optionally kicks off indexing helpers
    """
    _assert_main_thread()

    global _icon_theme
    _icon_theme = Gtk.IconTheme.get_default()

    # Theme watcher
    settings = Gtk.Settings.get_default()
    if settings:
        settings.connect("notify::gtk-icon-theme-name", _on_icon_theme_change)

    # DPI / monitor changes
    display = Gdk.Display.get_default()
    if display:
        display.connect("monitor-added", _rebuild_scale_and_clear_cache)
        display.connect("monitor-removed", _rebuild_scale_and_clear_cache)
    _rebuild_scale_and_clear_cache()

    # Optional background indices
    if desktop_index and hasattr(desktop_index, "build_index_async"):
        desktop_index.build_index_async()

    # Optional: build pkg → .desktop map, unless explicitly disabled
    if (
        pkg_desktop_map
        and hasattr(pkg_desktop_map, "build_pkg_map_async")
        and os.environ.get("SOFTWARE_STATION_DISABLE_PKG_MAP") != "1"
    ):
        pkg_desktop_map.build_pkg_map_async()

def _load_icon_pixbuf_main(icon_name: Optional[str], size: int = 32) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Main-thread ONLY. HiDPI-aware with robust fallback. Cached.
    """
    _assert_main_thread()
    assert _icon_theme is not None

    key = ((icon_name or ICON_FALLBACK), size, _scale)
    if key in _pixbuf_cache:
        return _pixbuf_cache[key]

    name = icon_name or ICON_FALLBACK
    pix: Optional[GdkPixbuf.Pixbuf] = None
    try:
        # Prefer lookup_icon_for_scale if present
        if hasattr(_icon_theme, "lookup_icon_for_scale"):
            info = _icon_theme.lookup_icon_for_scale(name, size, _scale, 0)
            if not info:
                info = _icon_theme.lookup_icon_for_scale(ICON_FALLBACK, size, _scale, 0)
            if info:
                pix = info.load_icon()
        else:
            if _icon_theme.has_icon(name):
                pix = _icon_theme.load_icon(name, size, 0)
            elif _icon_theme.has_icon(ICON_FALLBACK):
                pix = _icon_theme.load_icon(ICON_FALLBACK, size, 0)
    except Exception:
        # best-effort final fallback
        try:
            if _icon_theme.has_icon(ICON_FALLBACK):
                pix = _icon_theme.load_icon(ICON_FALLBACK, size, 0)
        except Exception:
            pix = None

    _pixbuf_cache[key] = pix
    return pix

@lru_cache(maxsize=4096)
def _friendly_name_guess(pkg_or_token: str) -> Optional[str]:
    """
    Try desktop_index first (localized Name), else None.
    """
    if not desktop_index:
        return None
    try:
        hit = desktop_index.best_guess(pkg_or_token)
        if hit and isinstance(hit, dict):
            return hit.get("name")
    except Exception:
        return None
    return None

@lru_cache(maxsize=4096)
def _icon_name_guess(pkg_or_token: str) -> Optional[str]:
    """
    Try desktop_index first (Icon=), else None.
    """
    if not desktop_index:
        return None
    try:
        hit = desktop_index.best_guess(pkg_or_token)
        if hit and isinstance(hit, dict):
            return hit.get("icon")
    except Exception:
        return None
    return None

def _resolve_label_and_icon_name_worker(pkg_name: str, curated_map: dict) -> tuple[str, Optional[str]]:
    """
    Worker thread: decide (label, icon_name STRING). No GTK here.
    Order:
      1) curated_map
      2) pkg → desktop (optional, via pkg_desktop_map → desktop_index)
      3) desktop_index.best_guess(pkg_name)
      4) fallback: pkg_name + None
    """
    # 1) curated
    info = curated_map.get(pkg_name, {})
    friendly = info.get("name")
    icon_name = info.get("icon")

    # 2) pkg → desktop path → desktop_index
    if (not friendly or not icon_name) and pkg_desktop_map and hasattr(pkg_desktop_map, "desktop_for_pkg"):
        try:
            desktop_path = pkg_desktop_map.desktop_for_pkg(pkg_name)
            if desktop_path and desktop_index:
                desktop_id = os.path.basename(desktop_path)
                hit = desktop_index.best_guess(desktop_id)
                if hit and isinstance(hit, dict):
                    if not friendly:
                        friendly = hit.get("name")
                    if not icon_name:
                        icon_name = hit.get("icon")
        except Exception:
            pass

    # 3) direct desktop_index lookup
    if not friendly or not icon_name:
        name_guess = _friendly_name_guess(pkg_name)
        icon_guess = _icon_name_guess(pkg_name)
        if not friendly and name_guess:
            friendly = name_guess
        if not icon_name and icon_guess:
            icon_name = icon_guess

    # 4) fallback
    if not friendly:
        friendly = pkg_name

    return (friendly, icon_name)

def resolve_label_and_icon_sync(
    pkg_name: str,
    curated_map: dict,
    size: int = 32
) -> Tuple[str, Optional[GdkPixbuf.Pixbuf]]:
    """
    Synchronous resolution (must run on main thread).
    Returns (label, pixbuf).
    """
    _assert_main_thread()
    label, icon_name = _resolve_label_and_icon_name_worker(pkg_name, curated_map)
    pixbuf = _load_icon_pixbuf_main(icon_name, size)
    return (label, pixbuf)

def resolve_label_and_icon_async(
    pkg_name: str,
    curated_map: dict,
    size: int,
    on_ready: Callable[[str, Optional[GdkPixbuf.Pixbuf]], None]
):
    """
    Asynchronous resolution: spawn worker to determine (label, icon_name),
    then load pixbuf on main thread and invoke callback on main thread.
    """
    def worker():
        label, icon_name = _resolve_label_and_icon_name_worker(pkg_name, curated_map)
        
        def main_thread_finish():
            pixbuf = _load_icon_pixbuf_main(icon_name, size)
            on_ready(label, pixbuf)
        
        GLib.idle_add(main_thread_finish)
    
    _executor.submit(worker)
