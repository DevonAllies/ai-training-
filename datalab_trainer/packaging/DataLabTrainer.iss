; Inno Setup script for DataLab Trainer  (https://jrsoftware.org/isinfo.php)
; Build:  iscc /DMyAppVersion=1.1.0 packaging\DataLabTrainer.iss   (from the datalab_trainer folder)
; Expects the PyInstaller output in dist\DataLabTrainer\ (see packaging\datalab.spec).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "DataLab Trainer"
#define MyAppExe "DataLabTrainer.exe"

[Setup]
AppId={{B3C1E5A2-7F4D-4E8B-9A62-1D5F3C7E9B40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=DataLab Trainer
DefaultDirName={autopf}\DataLabTrainer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt); the user can choose all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=DataLabTrainer-Setup-{#MyAppVersion}
SetupIconFile=datalab.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
VersionInfoVersion={#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\DataLabTrainer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "https://cran.r-project.org/bin/windows/base/"; Description: "Download R for the R exercises (opens your browser)"; Flags: shellexec postinstall skipifsilent unchecked; Check: not RInstalled
Filename: "{app}\{#MyAppExe}"; Description: "Start {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExe}"; Flags: runhidden; RunOnceId: "StopDataLab"

[UninstallDelete]
; Program files only - your progress, code and reports in %APPDATA%\DataLabTrainer are kept.
Type: filesandordirs; Name: "{app}"

[Code]
function RInstalled(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\R-core\R') or RegKeyExists(HKCU, 'SOFTWARE\R-core\R')
            or RegKeyExists(HKLM64, 'SOFTWARE\R-core\R');
end;
