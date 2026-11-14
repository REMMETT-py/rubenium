; RubeniumSetup.exe: installs Rubenium for the current user (no admin rights needed), with a Start menu
; entry and an uninstaller. Updates run this same setup silently. Built by GitHub Actions:
;   iscc /DVersion=1.0.0 /DVersionName=1.0 installer.iss
#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef VersionName
  #define VersionName Version
#endif

[Setup]
AppId={{6B0F2B7E-6E1D-4C8A-9F21-3D7A51C0B7A2}
AppName=Rubenium
AppVersion={#Version}
AppVerName=Rubenium {#VersionName}
AppPublisher=Rubenium
AppPublisherURL=https://github.com/REMMETT-py/rubenium
AppSupportURL=https://github.com/REMMETT-py/rubenium/issues
AppUpdatesURL=https://github.com/REMMETT-py/rubenium/releases
VersionInfoVersion={#Version}
VersionInfoProductName=Rubenium
VersionInfoDescription=Rubenium setup
DefaultDirName={localappdata}\Programs\Rubenium
DisableDirPage=auto
DisableProgramGroupPage=yes
DisableReadyPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=out
OutputBaseFilename=RubeniumSetup
SetupIconFile=rubenium.ico
UninstallDisplayIcon={app}\Rubenium.exe
UninstallDisplayName=Rubenium
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
en.Running=Rubenium is running.%n%nRight-click the Rubenium icon next to the clock and choose Quit Rubenium, then press OK.
fr.Running=Rubenium est ouverte.%n%nFaites un clic droit sur l'icône Rubenium près de l'horloge, choisissez Quitter Rubenium, puis appuyez sur OK.
en.Desktop=Add a desktop shortcut
fr.Desktop=Ajouter un raccourci sur le bureau

[Tasks]
Name: "desktop"; Description: "{cm:Desktop}"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\Rubenium\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Rubenium"; Filename: "{app}\Rubenium.exe"
Name: "{userdesktop}\Rubenium"; Filename: "{app}\Rubenium.exe"; Tasks: desktop

[Registry]
; Rubenium adds itself to start with Windows from its own settings; the uninstaller removes that entry.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Rubenium"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Rubenium.exe"; Parameters: "--updated {param:RUBENIUMARGS|}"; Flags: nowait; Check: WizardSilent
Filename: "{app}\Rubenium.exe"; Description: "{cm:LaunchProgram,Rubenium}"; Flags: nowait postinstall; Check: not WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im Rubenium.exe /f"; Flags: runhidden; RunOnceId: "StopRubenium"

[Code]
const MUTEX = 'Local\Rubenium.SingleInstance';

function InitializeSetup(): Boolean;
var
  i: Integer;
begin
  { An update: the app has just closed itself. Give it a moment to finish. }
  i := 0;
  while CheckForMutexes(MUTEX) and (i < 80) do
  begin
    Sleep(250);
    i := i + 1;
  end;
  Result := True;
  while Result and CheckForMutexes(MUTEX) do
  begin
    if WizardSilent then
      Result := False
    else
      Result := MsgBox(CustomMessage('Running'), mbInformation, MB_OKCANCEL) = IDOK;
  end;
end;
