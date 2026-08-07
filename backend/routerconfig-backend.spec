# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the RouterConfig Pro backend.
# Produces a self-contained backend binary so the packaged desktop app
# needs no system Python. Build from the repo root:
#   pyinstaller backend/routerconfig-backend.spec --noconfirm --clean
#
# Output: dist/routerconfig-backend  (or .exe on Windows)

import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "aiosqlite",
    "paramiko",
    "cryptography.hazmat.backends.openssl",
    "cryptography.hazmat.backends.openssl.rsa",
    "cryptography.hazmat.backends.openssl.ec",
    "pydantic",
    "Crypto",
    "Crypto.Cipher",
    "Crypto.Hash",
    "Crypto.Util.Padding",
    "ecdsa",
]

# Collect everything under backend/api, backend/core, backend/services, etc.
# so lazy/string imports resolve.
hiddenimports += collect_submodules("api")
hiddenimports += collect_submodules("core")
hiddenimports += collect_submodules("services")
hiddenimports += collect_submodules("database")
hiddenimports += collect_submodules("models")
hiddenimports += collect_submodules("isp_adapters")

datas = collect_data_files("paramiko")

a = Analysis(
    ["main.py"],
    pathex=["backend"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["alembic", "tests", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="routerconfig-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="routerconfig-backend",
)
