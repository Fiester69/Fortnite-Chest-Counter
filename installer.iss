; Установщик Fortnite Chest Counter (Inno Setup 6)
#define AppName "Fortnite Chest Counter"

[Setup]
AppId={{6B1E5C0A-4F52-4C1B-9A55-C4E57C0D7A11}
AppName={#AppName}
AppVersion=1.0
AppPublisher=Chest Counter
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=ChestCounter_Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\ChestCounter.exe
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AppMutex=ChestCounterOverlay
CloseApplications=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: checkedonce

[Files]
Source: "dist\ChestCounter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ChestCounter.exe"; Tasks: desktopicon
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\ChestCounter.exe"

[Run]
Filename: "{app}\ChestCounter.exe"; Description: "Запустить Fortnite Chest Counter"; Flags: nowait postinstall skipifsilent
