@echo off

rem Choose correct python command to execute the OTP
rem ppythona -h >nul 2>&1 && (
rem     set PYTHON_CMD=ppythona
rem ) || (
rem     set PYTHON_CMD=ppython
rem )

rem A Temporary Solution as you HAVE to use a 64 bit Panda with the current database.
set PYTHON_CMD=C:\Panda3D-1.10.0-x64\python\ppython.exe

cd ../

rem Start the OTP using the PYTHON_CMD variable
:main
%PYTHON_CMD% -m realtime.main
pause
goto :main
