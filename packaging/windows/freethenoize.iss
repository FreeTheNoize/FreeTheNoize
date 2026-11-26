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

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Upgrades: drop the previous version's libraries so no stale module survives.
Type: filesandordirs; Name: "{app}\_internal"

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
