; ============================================================
;  FeasFlow — Inno Setup installer script
;  Packages the PyInstaller onedir build (dist\FeasFlow\) into
;  a single Windows setup .exe with Start-menu / desktop shortcuts
;  and a proper uninstaller (Control Panel > Programs).
;
;  Compile:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" FeasFlow_installer.iss
;  Output:   Output\FeasFlow_Setup.exe
; ============================================================

#define MyAppName "FeasFlow"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "Alongkorn Chanta"
#define MyAppExeName "FeasFlow.exe"

[Setup]
AppId={{B7E4B0A2-9C31-4F2E-8A6D-FEA5F10W2026}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
; --- Install per-user so NO administrator rights are required ---
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; App icon shown in Add/Remove Programs
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Compression
Compression=lzma2/max
SolidCompression=yes
; Output installer
OutputDir=Output
OutputBaseFilename=FeasFlow_Setup
WizardStyle=modern
; Thai + English wizard
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkablealone

[Files]
; Bundle the entire onedir output (FeasFlow.exe + _internal\ + README)
Source: "dist\FeasFlow\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
