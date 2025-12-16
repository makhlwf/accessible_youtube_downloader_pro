# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['source\\accessible_youtube_downloader_pro.py'],
    pathex=[],
    binaries=[],
    datas=[('source\\api-ms-win-core-path-l1-1-0.dll', '.'), ('source\\avcodec-60.dll', '.'), ('source\\avdevice-60.dll', '.'), ('source\\avfilter-9.dll', '.'), ('source\\avformat-60.dll', '.'), ('source\\avutil-58.dll', '.'), ('source\\ffmpeg.exe', '.'), ('source\\ffplay.exe', '.'), ('source\\ffprobe.exe', '.'), ('source\\libvlc.dll', '.'), ('source\\libvlccore.dll', '.'), ('source\\nvdaControllerClient32.dll', '.'), ('source\\nvdaControllerClient64.dll', '.'), ('source\\postproc-57.dll', '.'), ('source\\swresample-4.dll', '.'), ('source\\swscale-7.dll', '.'), ('source\\assets', 'assets'), ('source\\docs', 'docs'), ('source\\languages', 'languages'), ('source\\plugins', 'plugins')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='accessible_youtube_downloader_pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='accessible_youtube_downloader_pro',
)
