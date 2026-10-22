; 版本以 csproj 为唯一真源,build.ps1 经 /DAppVer 注入;直接编译本脚本时回退 1.0.0
#ifndef AppVer
  #define AppVer "1.0.0"
#endif
; 打包源目录:build.ps1 传入干净 staging(build\setup_stage),直接编译时回退 dist
#ifndef SrcDir
  #define SrcDir "dist"
#endif

[Setup]
AppName=AgentEye
AppVersion={#AppVer}
AppPublisher=AgentEye Project
; 显式 AppId:升级链依赖它稳定(隐式取 AppName,改名即断链)
AppId=AgentEye
DefaultDirName=E:\AgentEye
; auto:首装显示目录页,升级(同 AppId)隐藏并沿用旧目录
DisableDirPage=auto
UsePreviousAppDir=yes
MinVersion=10.0.19041
DefaultGroupName=AgentEye
OutputDir=installer
OutputBaseFilename=AgentEye_Setup
Compression=lzma2/max
SolidCompression=yes
UninstallDisplayIcon={app}\AgentEye.exe
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; 静默安装时自动关掉正在运行的 AgentEye(用 Restart Manager)并替换文件,装完自动重启
; 应用内「下载并安装」就走这条路:拉起本安装器 + /VERYSILENT
CloseApplications=yes
RestartApplications=yes
; 不设 AppMutex:它会让 Setup 弹窗等用户手动关闭,静默升级会卡住

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动 AgentEye"; GroupDescription: "启动选项："; Flags: unchecked

[Files]
; 发布产物(框架依赖:运行时用系统装的 .NET 8 Desktop Runtime + Windows App Runtime);
; 双保险:排除一切用户数据与更新缓存
Source: "{#SrcDir}\*"; DestDir: "{app}"; Excludes: "AgentEye_Setup.exe,config.json"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AgentEye"; Filename: "{app}\AgentEye.exe"
; 用 {userdesktop} 而非 {commondesktop}:后者是 C:\Users\Public\Desktop,
; 非管理员安装(PrivilegesRequired=lowest)写不进去,快捷方式会静默失败
Name: "{userdesktop}\AgentEye"; Filename: "{app}\AgentEye.exe"; Tasks: desktopicon
Name: "{group}\说明 (README)"; Filename: "{app}\README.md"
Name: "{group}\卸载 AgentEye"; Filename: "{uninstallexe}"

[Registry]
; 开机自启(HKCU,无需管理员);应用内不提供开关,要关就在任务管理器→启动里禁用
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AgentEye"; ValueData: """{app}\AgentEye.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\AgentEye.exe"; Description: "启动 AgentEye"; Flags: postinstall nowait skipifsilent shellexec
