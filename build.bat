@echo off
rem Builds dist\Rubenium\Rubenium.exe on your own PC (GitHub also builds it automatically for every new version).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo Install Python 3.10-3.13 from python.org first. & pause & exit /b 1)
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller || (pause & exit /b 1)
for /f "tokens=3 delims= " %%v in ('findstr /b /c:"VERSION = " Rubenium.py') do set VER=%%~v
%PY% make_icon.py || (pause & exit /b 1)
%PY% make_version_info.py %VER% || (pause & exit /b 1)
%PY% -m PyInstaller --noconfirm --clean Rubenium.spec || (pause & exit /b 1)
echo.
echo Done: dist\Rubenium\Rubenium.exe   (installer.iss makes RubeniumSetup.exe with Inno Setup)
pause
