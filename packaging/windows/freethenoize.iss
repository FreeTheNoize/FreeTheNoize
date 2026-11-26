; Windows installer (Inno Setup 6). Built in CI from the PyInstaller folder:
;   iscc /DAppVersion=X.Y.Z /DSourceDir=dist\FreeTheNoize /DWebView2Setup=MicrosoftEdgeWebview2Setup.exe packaging\windows\freethenoize.iss
;
; Why an installer and not only the zip: Explorer copies the "downloaded from
; the Internet" mark to every file it extracts, .NET then refuses pythonnet and
; WebView2, and the app opened in the browser. Files written by the installer
; carry no mark, and Defender scans one download instead of ~1500 loose files.
;
; Per-user install (no admin): %LOCALAPPDATA%\Programs\FreeTheNoize.
; User data (%LOCALAPPDATA%\FreeTheNoize, music folder) is never touched.

#ifndef AppVersion
  #error Pass /DAppVersion=X.Y.Z
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\FreeTheNoize"
#endif

#define AppName "FreeTheNoize"
#define AppExe "FreeTheNoize.exe"

[Setup]
; Never change AppId: it is how upgrades find the previous install.
AppId={{53AEF833-7AED-4A46-A2C1-DEF78E1A0189}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=FreeTheNoize
AppPublisherURL=https://github.com/FreeTheNoize/FreeTheNoize
AppSupportURL=https://github.com/FreeTheNoize/FreeTheNoize/issues
AppUpdatesURL=https://github.com/FreeTheNoize/FreeTheNoize/releases
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableDirPage=auto
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\dist
OutputBaseFilename=FreeTheNoize-Windows-x64-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\..\LICENSE
WizardStyle=modern
; No language prompt: it blocked silent installs. Uses the Windows UI language.
ShowLanguageDialog=no
Compression=lzma2/max
SolidCompression=yes
; Close a running FreeTheNoize before replacing its files (Restart Manager).
CloseApplications=yes
RestartApplications=no
; The app holds this mutex while open (freethenoize/instance.py): setup and
; uninstall ask to close it first instead of failing on locked files.
AppMutex=FreeTheNoizeApp
; Only one setup at a time (two double-clicks on the download).
SetupMutex=FreeTheNoizeSetup,Global\FreeTheNoizeSetup

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Upgrades: drop the previous version's libraries so no stale module survives.
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
; Anything created inside the install folder after setup (none expected, but
; the folder must not survive an uninstall).
Type: filesandordirs; Name: "{app}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef WebView2Setup
Source: "{#WebView2Setup}"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: deleteafterinstall; Check: NeedsWebView2
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
#ifdef WebView2Setup
; The window needs the WebView2 runtime (built into Windows 11, missing on some Windows 10).
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando Microsoft Edge WebView2..."; Check: NeedsWebView2; Flags: waituntilterminated
#endif
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  AppIdKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{53AEF833-7AED-4A46-A2C1-DEF78E1A0189}_is1';
  WebView2Key = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Version(Root: Integer; Key: String): String;
begin
  if not RegQueryStringValue(Root, Key, 'pv', Result) then
    Result := '';
end;

function HasVersion(V: String): Boolean;
begin
  Result := (V <> '') and (V <> '0.0.0.0');
end;

// Microsoft's documented check: machine-wide (32-bit view) or per-user install.
function NeedsWebView2(): Boolean;
begin
  Result := not (HasVersion(WebView2Version(HKLM, 'SOFTWARE\WOW6432Node\' + WebView2Key))
              or HasVersion(WebView2Version(HKLM, 'SOFTWARE\' + WebView2Key))
              or HasVersion(WebView2Version(HKCU, 'Software\' + WebView2Key)));
end;

// Compares dotted versions ("3.10.0" > "3.9.2"): >0, 0 or <0.
function CompareVersions(A, B: String): Integer;
var
  PA, PB, NA, NB: Integer;
begin
  Result := 0;
  while (Result = 0) and ((A <> '') or (B <> '')) do
  begin
    PA := Pos('.', A); if PA = 0 then PA := Length(A) + 1;
    PB := Pos('.', B); if PB = 0 then PB := Length(B) + 1;
    NA := StrToIntDef(Copy(A, 1, PA - 1), 0);
    NB := StrToIntDef(Copy(B, 1, PB - 1), 0);
    Result := NA - NB;
    Delete(A, 1, PA);
    Delete(B, 1, PB);
  end;
end;

// Installing an older version over a newer one: confirm (interactive only).
function InitializeSetup(): Boolean;
var
  Installed: String;
begin
  Result := True;
  if RegQueryStringValue(HKCU, AppIdKey, 'DisplayVersion', Installed) and
     (CompareVersions(Installed, '{#AppVersion}') > 0) and not WizardSilent() then
    Result := MsgBox('Ya tienes instalada FreeTheNoize ' + Installed + ', más nueva que esta (' +
                     '{#AppVersion}' + ').' + #13#10#13#10 + '¿Instalar la versión anterior de todos modos?',
                     mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

// Uninstall: the program always goes; the user's data only if they say so
// (/PURGE=1 for silent uninstalls). The music folder is never touched.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Purge: Boolean;
  Code: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  if UninstallSilent() then
    Purge := ExpandConstant('{param:PURGE|0}') = '1'
  else
    Purge := MsgBox('¿Borrar también tus ajustes, historial y caché de FreeTheNoize?' + #13#10#13#10 +
                    'Tu música no se borra en ningún caso.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  if Purge then
  begin
    DelTree(ExpandConstant('{localappdata}\FreeTheNoize'), True, True, True);
    // SoundCloud session stored in Windows Credential Manager (keyring).
    Exec(ExpandConstant('{sys}\cmdkey.exe'), '/delete:FreeTheNoize', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Exec(ExpandConstant('{sys}\cmdkey.exe'), '/delete:soundcloud-oauth@FreeTheNoize', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;
