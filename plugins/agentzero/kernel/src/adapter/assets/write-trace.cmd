@echo off
REM Cursor adapter: forward hook stdin to the Trace writer. Fail open.
set ROOT=%~dp0..\..
set PYTHONPATH=%ROOT%\src;%PYTHONPATH%
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -m traces.hook
) else (
  python -m traces.hook
)
