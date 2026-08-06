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
english.UninstallConfirmTitle=Uninstall Medical Redactor
english.UninstallConfirmPrompt=Do you want to uninstall Medical Redactor?
english.RemoveDownloadedModelsCheckbox=Also remove the downloaded HuBERT and TableFormer model files
english.UninstallYesButton=&Yes
english.UninstallNoButton=&No
hungarian.UninstallConfirmTitle=Az Orvosi dokumentum anonimizáló eltávolítása
hungarian.UninstallConfirmPrompt=El szeretné távolítani az Orvosi dokumentum anonimizálót?
hungarian.RemoveDownloadedModelsCheckbox=A letöltött HuBERT és TableFormer modellfájlok is törlődjenek
hungarian.UninstallYesButton=&Igen
hungarian.UninstallNoButton=&Nem

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

function HasCommandLineParameter(Value: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Value) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

function ShowUninstallConfirmation(): Boolean;
var
  Form: TSetupForm;
  PromptLabel: TNewStaticText;
  RemoveModelsCheck: TNewCheckBox;
  YesButton: TNewButton;
  NoButton: TNewButton;
begin
  Form := CreateCustomForm(ScaleX(440), ScaleY(150), False, False);
  try
    Form.Caption := ExpandConstant('{cm:UninstallConfirmTitle}');
    Form.Position := poScreenCenter;

    PromptLabel := TNewStaticText.Create(Form);
    PromptLabel.Parent := Form;
    PromptLabel.AutoSize := False;
    PromptLabel.WordWrap := True;
    PromptLabel.Caption := ExpandConstant('{cm:UninstallConfirmPrompt}');
    PromptLabel.SetBounds(ScaleX(16), ScaleY(16), ScaleX(408), ScaleY(42));

    RemoveModelsCheck := TNewCheckBox.Create(Form);
    RemoveModelsCheck.Parent := Form;
    RemoveModelsCheck.Caption := ExpandConstant(
      '{cm:RemoveDownloadedModelsCheckbox}'
    );
    RemoveModelsCheck.Checked := True;
    RemoveModelsCheck.SetBounds(
      ScaleX(16), ScaleY(66), ScaleX(408), ScaleY(24)
    );

    YesButton := TNewButton.Create(Form);
    YesButton.Parent := Form;
    YesButton.Caption := ExpandConstant('{cm:UninstallYesButton}');
    YesButton.Default := True;
    YesButton.ModalResult := mrOk;
    YesButton.SetBounds(ScaleX(268), ScaleY(106), ScaleX(75), ScaleY(25));

    NoButton := TNewButton.Create(Form);
    NoButton.Parent := Form;
    NoButton.Caption := ExpandConstant('{cm:UninstallNoButton}');
    NoButton.Cancel := True;
    NoButton.ModalResult := mrCancel;
    NoButton.SetBounds(ScaleX(349), ScaleY(106), ScaleX(75), ScaleY(25));

    Form.ActiveControl := YesButton;
    Result := Form.ShowModal() = mrOk;
    RemoveDownloadedModels := RemoveModelsCheck.Checked;
  finally
    Form.Free();
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  UninstallKey: String;
begin
  if CurStep = ssPostInstall then
  begin
    UninstallKey :=
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{D328CBA3-9D65-4A28-A3D0-0267CEAEAB5B}_is1';
    RegWriteStringValue(
      HKCU64,
      UninstallKey,
      'UninstallString',
      '"' + ExpandConstant('{uninstallexe}') + '" /SILENT'
    );
  end;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  RelaunchParameters: String;
begin
  RemoveDownloadedModels := True;

  if HasCommandLineParameter('/CUSTOMCONFIRMED') then
  begin
    RemoveDownloadedModels := not HasCommandLineParameter('/KEEPMODELS');
    Result := True;
    Exit;
  end;

  if HasCommandLineParameter('/VERYSILENT') or
     HasCommandLineParameter('/SUPPRESSMSGBOXES') then
  begin
    Result := True;
    Exit;
  end;

  if not ShowUninstallConfirmation() then
  begin
    Result := False;
    Exit;
  end;

  if UninstallSilent() then
  begin
    Result := True;
    Exit;
  end;

  RelaunchParameters := '/SILENT /CUSTOMCONFIRMED /LANG=' +
    ExpandConstant('{language}');
  if not RemoveDownloadedModels then
    RelaunchParameters := RelaunchParameters + ' /KEEPMODELS';

  Result := False;
  Exec(
    ExpandConstant('{uninstallexe}'),
    RelaunchParameters,
    '',
    SW_SHOWNORMAL,
    ewNoWait,
    ResultCode
  );
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
