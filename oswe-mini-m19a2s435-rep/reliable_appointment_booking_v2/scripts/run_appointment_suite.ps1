# PowerShell script to run appointment suite
Set-StrictMode -Version Latest
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
python $root\..\tests\run_suite.py
