# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for kiln.

Build with:
    pyinstaller kiln.spec

This creates a single-file executable in dist/kiln
"""

import sys
from pathlib import Path

# Get the source directory
src_dir = Path("src")

a = Analysis(
    ["src/cli.py"],
    pathex=[],
    binaries=[],
    datas=[(".env.example", "."), ("README.md", "."), (".claude/commands", ".claude/commands")],
    hiddenimports=[
        # OpenTelemetry requires explicit imports
        "opentelemetry",
        "opentelemetry.sdk",
        "opentelemetry.sdk.trace",
        "opentelemetry.sdk.resources",
        "opentelemetry.exporter.otlp",
        "opentelemetry.exporter.otlp.proto.http",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        # YAML
        "yaml",
        # Our modules
        "src",
        "src.cli",
        "src.config",
        "src.daemon",
        "src.database",
        "src.logger",
        "src.telemetry",
        "src.workspace",
        "src.claude_runner",
        "src.comment_processor",
        "src.interfaces",
        "src.interfaces.ticket",
        "src.ticket_clients",
        "src.ticket_clients.github",
        "src.workflows",
        "src.workflows.base",
        "src.workflows.implement",
        "src.workflows.plan",
        "src.workflows.prepare",
        "src.workflows.process_comments",
        "src.workflows.research",
        "src.workflows.test_access",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude dev/test dependencies
        "pytest",
        "pytest_asyncio",
        "ruff",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="kiln",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
