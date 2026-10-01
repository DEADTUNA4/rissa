@echo off
REM Build rissa native Win32 GUI with w64devkit GCC. Run from gui_native\.
REM Embeds the comctl-v6 manifest (themed controls) + PerMonitorV2 DPI awareness.
set PATH=E:\w64devkit\bin;%PATH%
windres rissa_gui.rc -o rissa_gui_res.o
if errorlevel 1 (echo RES FAILED & exit /b 1)
gcc.exe -O2 -Wall -municode -mwindows rissa_gui.c rissa_gui_res.o -o rissa_gui.exe -lgdi32 -lcomdlg32 -lcomctl32 -lshell32
if errorlevel 1 (echo BUILD FAILED & exit /b 1)
echo BUILD OK: gui_native\rissa_gui.exe
