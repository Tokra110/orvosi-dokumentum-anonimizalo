; Inno Setup definition for the standard Windows per-user installer.
; Build from the repository root after PyInstaller has produced
; dist\medical-redactor:
;   ISCC.exe /DMyAppVersion=0.1.0 /DMyAppNumericVersion=0.1.0 packaging\medical-redactor.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#ifndef MyAppNumericVersion
  #define MyAppNumericVersion "0.1.0"
#endif

#define MyAppName "Orvosi dokumentum anonimizáló"
#define MyAppPublisher "Medical Redactor contributors"
#define MyAppExeName "medical-redactor.exe"

[Setup]
AppId={{D328CBA3-9D65-4A28-A3D0-0267CEAEAB5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppNumericVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppNumericVersion}
VersionInfoCompany={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Medical Redactor
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=medical-redactor-{#MyAppVersion}-windows-x86_64-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\medical-redactor.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.RemoveDownloadedModelsPrompt=Also remove the downloaded HuBERT and TableFormer models?%n%nChoose No to keep them for a later reinstall.
hungarian.RemoveDownloadedModelsPrompt=A letöltött HuBERT és TableFormer modellek is törlődjenek?%n%nVálassza a Nem lehetőséget, ha meg szeretné tartani őket egy későbbi újratelepítéshez.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\medical-redactor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: postinstall nowait skipifsilent

[Code]
var
  RemoveDownloadedModels: Boolean;

function InitializeUninstall(): Boolean;
var
  Answer: Integer;
begin
  Answer := SuppressibleMsgBox(
    ExpandConstant('{cm:RemoveDownloadedModelsPrompt}'),
    mbConfirmation,
    MB_YESNOCANCEL,
    IDYES
  );
  Result := Answer <> IDCANCEL;
  RemoveDownloadedModels := Answer = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and RemoveDownloadedModels then
  begin
    DelTree(ExpandConstant('{app}\models'), True, True, True);
    DelTree(
      ExpandConstant('{localappdata}\medical-redactor\models'),
      True,
      True,
      True
    );
  end;
end;
