Unicode True
Name "EQ Watcher"
OutFile "..\EQ-Watcher-Setup-windows-x64.exe"
InstallDir "$LOCALAPPDATA\EQ Watcher"
RequestExecutionLevel user
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\EQ-Watcher\*"
  CreateDirectory "$SMPROGRAMS\EQ Watcher"
  CreateShortcut "$SMPROGRAMS\EQ Watcher\EQ Watcher.lnk" "$INSTDIR\EQ-Watcher.exe"
  CreateShortcut "$DESKTOP\EQ Watcher.lnk" "$INSTDIR\EQ-Watcher.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EQ Watcher" "DisplayName" "EQ Watcher"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EQ Watcher" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EQ Watcher" "DisplayVersion" "1.0.0"
SectionEnd
Section "Uninstall"
  Delete "$DESKTOP\EQ Watcher.lnk"
  RMDir /r "$SMPROGRAMS\EQ Watcher"
  Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\EQ Watcher.cmd"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EQ Watcher"
SectionEnd
