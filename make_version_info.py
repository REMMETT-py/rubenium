"""Writes version_info.txt (the version shown in the .exe's Properties) from a version like 2.2.0."""
import sys

v = (sys.argv[1] if len(sys.argv) > 1 else "0.0.0").split(".")
nums = tuple(int(x) for x in (v + ["0", "0", "0", "0"])[:4])
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
          StringStruct('CompanyName', 'Rubenium'), StringStruct('FileDescription', 'Rubenium'),
          StringStruct('FileVersion', '{".".join(map(str, nums[:3]))}'), StringStruct('InternalName', 'Rubenium'),
          StringStruct('OriginalFilename', 'Rubenium.exe'), StringStruct('ProductName', 'Rubenium'),
          StringStruct('ProductVersion', '{".".join(map(str, nums[:3]))}')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""
open("version_info.txt", "w", encoding="utf-8").write(text)
print("version_info.txt for", nums)
