#define MyAppName "HexPlayer"
#define MyAppExeName "HexPlayer.exe"
#define MyAppVersion "4.2.0"
#define MyAppPublisher "makhlwf"
#define MyAppURL "https://github.com/makhlwf/accessible_youtube_downloader_pro"
#define RepoRoot "..\..\"

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
OutputDir={#RepoRoot}HexPlayer
OutputBaseFilename=HexPlayer
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=2
LZMAUseSeparateProcess=yes
InternalCompressLevel=ultra
WizardStyle=modern dark polar includetitlebar
LicenseFile={#RepoRoot}PRIVACY_POLICY.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Messages]
english.WizardLicense=Privacy Policy
english.LicenseLabel=Please read the following Privacy Policy. You must accept it before continuing setup.
english.LicenseLabel3=Please accept the Privacy Policy before continuing.
english.LicenseAccepted=I accept the Privacy Policy
english.LicenseNotAccepted=I do not accept the Privacy Policy
arabic.WizardLicense=سياسة الخصوصية
arabic.LicenseLabel=يرجى قراءة سياسة الخصوصية التالية. يجب قبولها قبل متابعة التثبيت.
arabic.LicenseLabel3=يرجى قبول سياسة الخصوصية قبل المتابعة.
arabic.LicenseAccepted=أوافق على سياسة الخصوصية
arabic.LicenseNotAccepted=لا أوافق على سياسة الخصوصية

[CustomMessages]
english.DownloadYtDlp=Download latest yt-dlp library (recommended)
arabic.DownloadYtDlp=تحميل أحدث إصدار من مكتبة yt-dlp (موصى به)

english.DownloadDeno=Download Deno (recommended for YouTube)
arabic.DownloadDeno=تحميل Deno (موصى به لليوتيوب)

english.DownloadTitle=Downloading components
arabic.DownloadTitle=جاري تحميل المكونات

english.DownloadDesc=Please wait while additional files are downloaded.
arabic.DownloadDesc=يرجى الانتظار أثناء تحميل الملفات الإضافية.

english.NoInternet=Internet connection not detected.%n%nComponents were not downloaded.
arabic.NoInternet=لم يتم اكتشاف اتصال بالإنترنت.%n%nلم يتم تحميل المكونات.

english.DownloadFailed=Failed to download some components.%n%nyou can download them manually later.
arabic.DownloadFailed=فشل تحميل بعض المكونات.%n%nيمكنك تحميلها يدويًا لاحقًا.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "download_ytdlp"; Description: "{cm:DownloadYtDlp}"; Flags: unchecked
Name: "download_deno"; Description: "{cm:DownloadDeno}"; Flags: unchecked

[Files]
Source: "{#RepoRoot}dist\HexPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}dist\HexPlayer\_internal\browser_extension\*"; DestDir: "{userappdata}\HexPlayer\browser_extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\browser_extension"
Type: filesandordirs; Name: "{app}\_internal\browser_extension"
Type: filesandordirs; Name: "{userappdata}\HexPlayer\browser_extension"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  YtDlpUrl = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp';
  DenoUrl = 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip';

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

procedure DownloadComponents;
var
  YtDlpTargetFile: string;
  DenoTargetFile: string;
  DenoZipFile: string;
  TargetDir: string;
  DownloadYtDlp: Boolean;
  DownloadDeno: Boolean;
  ResultCode: Integer;
begin
  YtDlpTargetFile := ExpandConstant('{userappdata}\HexPlayer\yt_dlp.zip');
  DenoTargetFile := ExpandConstant('{app}\deno.exe');
  DenoZipFile := ExpandConstant('{tmp}\deno.zip');
  TargetDir := ExpandConstant('{app}');

  DownloadYtDlp := (WizardIsTaskSelected('download_ytdlp') or (ExpandConstant('{param:DownloadComponents|0}') = '1')) and not FileExists(YtDlpTargetFile);
  DownloadDeno := (WizardIsTaskSelected('download_deno') or (ExpandConstant('{param:DownloadComponents|0}') = '1')) and not FileExists(DenoTargetFile);

  if not (DownloadYtDlp or DownloadDeno) then
    Exit;

  if not IsOnline then
  begin
    if not WizardSilent then
      MsgBox(ExpandConstant('{cm:NoInternet}'), mbInformation, MB_OK);
    Exit;
  end;

  if not DirExists(TargetDir) then
    ForceDirectories(TargetDir);

  if DownloadYtDlp then
    ForceDirectories(ExtractFilePath(YtDlpTargetFile));

  DownloadPage := CreateDownloadPage(
    ExpandConstant('{cm:DownloadTitle}'),
    ExpandConstant('{cm:DownloadDesc}'),
    nil
  );
  DownloadPage.Clear;
  if DownloadYtDlp then
    DownloadPage.Add(YtDlpUrl, 'yt_dlp.zip', '');
  if DownloadDeno then
    DownloadPage.Add(DenoUrl, 'deno.zip', '');

  DownloadPage.Show;

  try
    try
      DownloadPage.Download;

      if DownloadYtDlp then
      begin
        if not FileCopy(ExpandConstant('{tmp}\yt_dlp.zip'), YtDlpTargetFile, False) then
          if not WizardSilent then
            MsgBox(ExpandConstant('{cm:DownloadFailed}'), mbError, MB_OK);
      end;

      if DownloadDeno then
      begin
        // Extract deno.exe from zip using PowerShell
        if Exec('powershell.exe', ExpandConstant('-NoProfile -Command "Expand-Archive -Path ''{tmp}\deno.zip'' -DestinationPath ''{app}'' -Force"'), '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        begin
          if not FileExists(DenoTargetFile) then
             if not WizardSilent then
               MsgBox(ExpandConstant('{cm:DownloadFailed}'), mbError, MB_OK);
          // Delete the zip file after extraction
          DeleteFile(DenoZipFile);
        end
        else
          if not WizardSilent then
            MsgBox(ExpandConstant('{cm:DownloadFailed}'), mbError, MB_OK);
      end;

    except
      if not DownloadPage.AbortedByUser then
        if not WizardSilent then
          MsgBox(ExpandConstant('{cm:DownloadFailed}'), mbError, MB_OK);
    end;
  finally
    DownloadPage.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) then
  begin
    DownloadComponents;
  end;
end;
