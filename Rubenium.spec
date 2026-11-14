# -*- mode: python ; coding: utf-8 -*-
# Builds dist\Rubenium\ (Rubenium.exe and its files, no console window). installer.iss turns that folder into
# RubeniumSetup.exe. A folder app starts from where it is installed instead of unpacking itself on every start.
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hidden = [("swaps", "swaps")], [], []
try:
    d, b, h = collect_all("winrt")
    datas += d; binaries += b; hidden += h
except Exception:
    pass
try:
    hidden += collect_submodules("winrt")
except Exception:
    pass
hidden += ["winrt.windows.media.control", "winrt.windows.storage.streams", "winrt.windows.foundation",
           "winrt.windows.foundation.collections", "winrt.windows.media", "psutil"]

EXCLUDES = ["tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3", "sqlite3", "numpy", "PIL",
            "PyQt6.QtNetwork", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtSql", "PyQt6.QtSvg", "PyQt6.QtTest",
            "PyQt6.QtMultimedia", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtBluetooth",
            "PyQt6.QtDBus", "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets",
            "PyQt6.QtPdf", "PyQt6.QtPrintSupport", "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtXml",
            "PyQt6.Qt3DCore", "PyQt6.QtCharts", "PyQt6.QtPositioning", "PyQt6.QtRemoteObjects",
            "PyQt6.QtTextToSpeech", "PyQt6.QtWebChannel", "PyQt6.QtWebSockets", "PyQt6.QtNfc"]

a = Analysis(["Rubenium.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=EXCLUDES, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Rubenium", debug=False, strip=False, upx=False,
          console=False, uac_admin=False, icon="rubenium.ico", version="version_info.txt")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Rubenium")
