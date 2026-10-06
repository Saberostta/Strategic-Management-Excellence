@echo off
REM Weekly XRF report: drop the new workbook into the "inbox" folder, then double-click this file.
REM The newest .xlsx in inbox\ is processed; reports land in reports\ and history accumulates in data\history.csv.
cd /d "%~dp0"
for /f "delims=" %%F in ('dir /b /o-d inbox\*.xlsx 2^>nul') do (set "LATEST=inbox\%%F" & goto :run)
echo No .xlsx file found in inbox\ & pause & exit /b 1
:run
python -m xrf_report "%LATEST%" --history data\history.csv -o reports
if errorlevel 1 (pause & exit /b 1)
for /f "delims=" %%R in ('dir /b /o-d reports\*.html') do (start "" "reports\%%R" & goto :eof)
