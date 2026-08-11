"""Shared constants — no imports beyond stdlib, safe for any module."""

import os

TERMUX_PREFIX = "/data/data/com.termux/files/usr"

CONTAINER_NAME = "arinanolabs"
ADMIN_USER = "admin"
IMAGE_REF = "ghcr.io/arinadi/arinanolabs:latest"

PROOT_ROOT = f"{TERMUX_PREFIX}/var/lib/proot-distro"
PROOT_DIR = f"{PROOT_ROOT}/containers/{CONTAINER_NAME}"
CACHE_DIR = f"{PROOT_ROOT}/cache"

REPO_URL = "https://github.com/arinadi/arinanoLabs.git"
REPO_DIR = os.path.expanduser("~/arinanoLabs")

# Termux writes here; TMPDIR is set in a normal Termux session but not always
# in the environment a launcher inherits, so fall back explicitly.
TMPDIR = os.environ.get("TMPDIR", f"{TERMUX_PREFIX}/tmp")
