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
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_pkg_map: Dict[str, str] = {}
_ready = threading.Event()

def _run(cmd: list[str]) -> str:
    """
    Run a command, return stdout as text; swallow errors and stderr.
    
    Security: cmd must be a list to prevent shell injection.
    """
    if not isinstance(cmd, list):
        raise ValueError("Command must be a list to prevent shell injection")
    
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            shell=False  # Explicitly disable shell for security
        )
        return cp.stdout or ""
    except Exception as e:
        logger.debug(f"Command failed: {cmd}, error: {e}")
        return ""

def _process_package(pkg: str) -> tuple[str, Optional[str]]:
    """
    Process a single package to find its .desktop file.
    Returns (pkg_name, desktop_path or None).
    """
    # List files for this package
    listing = _run(["pkg", "info", "-l", pkg])
    if not listing:
        return (pkg, None)
    
    # Lines typically look like: "\t/usr/local/share/applications/foo.desktop"
    for line in listing.splitlines():
        path = line.strip()
        if path and path.endswith(".desktop"):
            return (pkg, path)
    
    return (pkg, None)

def build_pkg_map_async():
    """Build the pkg→desktop map in a background thread with parallel processing."""
    def work():
        try:
            # All installed package names, one per line
            pkgs_txt = _run(["pkg", "query", "%n"])
            if not pkgs_txt:
                logger.info("No packages found or pkg command failed")
                return
            
            pkgs = [p for p in pkgs_txt.splitlines() if p]
            logger.info(f"Processing {len(pkgs)} packages for desktop files")
            
            # Process packages in parallel for better performance
            processed = 0
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_process_package, pkg): pkg for pkg in pkgs}
                
                for future in as_completed(futures):
                    try:
                        pkg, desktop_path = future.result()
                        if desktop_path:
                            _pkg_map[pkg] = desktop_path
                        processed += 1
                        
                        # Log progress every 100 packages
                        if processed % 100 == 0:
                            logger.debug(f"Processed {processed}/{len(pkgs)} packages")
                    except Exception as e:
                        pkg = futures[future]
                        logger.debug(f"Failed to process package '{pkg}': {e}")
            
            logger.info(f"Built pkg→desktop map with {len(_pkg_map)} entries")
        except Exception as e:
            logger.error(f"Error building pkg→desktop map: {e}", exc_info=True)
        finally:
            _ready.set()
    
    threading.Thread(target=work, daemon=True).start()

def desktop_for_pkg(pkg: str) -> Optional[str]:
    """Return a known .desktop path for the package, if any."""
    return _pkg_map.get(pkg)
