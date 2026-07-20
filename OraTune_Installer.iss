[Setup]
AppName=OraTune
AppVersion=2.2.1
AppPublisher=OraTune
DefaultDirName={autopf}\OraTune
DefaultGroupName=OraTune
OutputDir=installer_output
OutputBaseFilename=OraTune_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\OraTune.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
MinVersion=10.0

[Files]
Source: "dist\OraTune.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\OraTune"; Filename: "{app}\OraTune.exe"
Name: "{group}\Uninstall OraTune"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OraTune"; Filename: "{app}\OraTune.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\OraTune.exe"; Description: "Launch OraTune"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var SettingsFile: String; Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    SettingsFile := ExpandConstant('{%USERPROFILE}\.oracletune_settings.json');
    if FileExists(SettingsFile) then
    begin
      Response := MsgBox('Delete saved settings and API keys?' + #13#10 + SettingsFile, mbConfirmation, MB_YESNO);
      if Response = IDYES then DeleteFile(SettingsFile);
    end;
  end;
end;
