; Inno Setup script for SimCoach  (https://jrsoftware.org/isinfo.php)
; Build:  iscc /DMyAppVersion=0.2.0 packaging\SimCoach.iss
; Expects the PyInstaller output in dist\SimCoach\ (see packaging\simcoach.spec).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "SimCoach"
#define MyAppExe "SimCoach.exe"

[Setup]
AppId={{6E2B1C7A-5D43-4F7E-9B1A-3C8D2E61F0A4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=SimCoach
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt); user can choose all-users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=SimCoach-Setup-{#MyAppVersion}
SetupIconFile=simcoach.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start SimCoach with &Windows (runs quietly in the tray)"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\SimCoach\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName} demo (no iRacing needed)"; Filename: "{app}\{#MyAppExe}"; Parameters: "--demo"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Same value the app's "Start with Windows" setting uses.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SimCoach"; ValueData: """{app}\{#MyAppExe}"" --no-browser"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch SimCoach now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExe}"; Flags: runhidden; RunOnceId: "StopSimCoach"

[UninstallDelete]
; Program files only - your laps, settings and imports in %APPDATA%\SimCoach are kept.
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { also remove the Run value if the user enabled autostart from inside the app }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'SimCoach');
end;
