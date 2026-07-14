!macro NSIS_HOOK_PREUNINSTALL
  ; Stop the background worker before NSIS replaces/removes the executable.
  ; User data in %APPDATA%\SiliciumNode is deliberately preserved so an
  ; upgrade or repair install keeps the node identity and task history.
  ExecWait '"$INSTDIR\${MAINBINARYNAME}.exe" --cleanup'
!macroend
