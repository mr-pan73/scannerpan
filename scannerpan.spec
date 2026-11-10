# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

project_dir = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(project_dir, 'resources'), 'resources'),
]

binaries = []
dll_dir = os.path.join(project_dir, 'resources', 'windows_dlls')
if os.path.isdir(dll_dir):
    for dll in ['icuuc.dll', 'icuin.dll', 'icudt.dll']:
        p = os.path.join(dll_dir, dll)
        if os.path.isfile(p):
            binaries.append((p, '.'))

hiddenimports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PIL',
    'PIL.Image',
    'PIL.ImageEnhance',
    'PIL.ImageFilter',
    'cv2',
    'docx',
    'odf',
    'pytesseract',
    'scannerpan',
    'scannerpan.ui',
    'scannerpan.ui.main_window',
    'scannerpan.ui.kde_theme',
    'scannerpan.ui.canvas',
    'scannerpan.ui.dialogs',
    'scannerpan.hardware',
    'scannerpan.hardware.sane_engine',
    'scannerpan.processing',
    'scannerpan.processing.cv_detector',
    'scannerpan.processing.ocr_engine',
    'scannerpan.processing.ocr_exporter',
    'scannerpan.processing.merger',
]

a = Analysis(
    [os.path.join(project_dir, 'scannerpan', 'app.py')],
    pathex=[project_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScannerPan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'resources', 'scannerpan.ico'),
)
