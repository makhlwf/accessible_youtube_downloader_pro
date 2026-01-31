#define MyAppName "HexPlayer"
#define MyAppExeName "HexPlayer.exe"
#define MyAppVersion "1.8.5"
#define MyAppPublisher "makhlwf"
#define MyAppURL "https://github.com/makhlwf/accessible_youtube_downloader_pro"

[Setup]
AppId={{08A53112-0E98-433F-8E55-2D92C3120947}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoTextVersion={#MyAppVersion}
VersionInfoCopyright=Copyright © {#MyAppPublisher}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=HexPlayer
OutputBaseFilename=HexPlayer
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.DownloadYtDlp=Download yt-dlp (recommended)
arabic.DownloadYtDlp=تحميل yt-dlp (موصى به)

english.DownloadTitle=Downloading components
arabic.DownloadTitle=جاري تحميل المكونات

english.DownloadDesc=Please wait while additional files are downloaded.
arabic.DownloadDesc=يرجى الانتظار أثناء تحميل الملفات الإضافية.

english.NoInternet=Internet connection not detected.%n%nyt-dlp was not downloaded.
arabic.NoInternet=لم يتم اكتشاف اتصال بالإنترنت.%n%nلم يتم تحميل yt-dlp.

english.DownloadFailed=Failed to download yt-dlp.%n%nyou can download it manually later.
arabic.DownloadFailed=فشل تحميل yt-dlp.%n%nيمكنك تحميله يدويًا لاحقًا.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "download_ytdlp"; Description: "{cm:DownloadYtDlp}"; Flags: unchecked

[Files]
Source: "C:\accessible_youtube_downloader_pro\dist\HexPlayer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\accessible_youtube_downloader_pro\dist\_internal\*"; DestDir: "{app}\_internal"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  YtDlpUrl = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe';

var
  DownloadPage: TDownloadWizardPage;

function IsOnline: Boolean;
var
  Req: Variant;
begin
  Result := False;
  try
    Req := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Req.Open('HEAD', 'https://github.com', False);
    Req.Send;
    Result := (Req.Status = 200);
  except
    Result := False;
  end;
end;

procedure DownloadYtDlp;
var
  TargetFile: string;
  TargetDir: string;
begin
  TargetFile := ExpandConstant('{app}\yt-dlp.exe');
  TargetDir := ExpandConstant('{app}');

  // 1. Skip if file already exists
  if FileExists(TargetFile) then
    Exit;

  // 2. Check internet connection
  if not IsOnline then
  begin
    MsgBox(ExpandConstant('{cm:NoInternet}'), mbInformation, MB_OK);
    Exit;
  end;

  // 3. Ensure the destination directory exists (safety measure)
  if not DirExists(TargetDir) then
    ForceDirectories(TargetDir);

  // 4. Initialize and show download page
  DownloadPage := CreateDownloadPage(
    ExpandConstant('{cm:DownloadTitle}'),
    ExpandConstant('{cm:DownloadDesc}'),
    nil
  );
  DownloadPage.Clear;
  DownloadPage.Add(YtDlpUrl, 'yt-dlp.exe', '');
  DownloadPage.Show;

  try
    try
      DownloadPage.Download;
      
      // 5. Copy from Temp to the final App folder
      if not FileCopy(ExpandConstant('{tmp}\yt-dlp.exe'), TargetFile, False) then
      begin
        MsgBox(ExpandConstant('{cm:DownloadFailed}'), mbError, MB_OK);
      end;
      
    except
      if not DownloadPage.AbortedByUser then
        MsgBox(ExpandConstant('{cm:DownloadFailed}'), mbError, MB_OK);
    end;
  finally
    DownloadPage.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // We use ssPostInstall because the {app} folder is created 
  // and fixed files are extracted BEFORE this step runs.
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('download_ytdlp') then
  begin
    DownloadYtDlp;
  end;
end;