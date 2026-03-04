@echo off
:: SpandaOS — The Living Pulse of Agentic Intelligence
:: A self-pulsing intelligence that lives at the core of the system — perpetually vibrating, continuously learning from every interaction, self-correcting its own errors, and driving all reasoning from a single living center — not because it was told to, but because that is its fundamental nature.
:: Copyright (C) 2026 Pankaj Umesh Varma
:: Contact: 9372123700
:: Email: pv43770@gmail.com
::
:: This program is free software: you can redistribute it and/or modify
:: it under the terms of the GNU Affero General Public License as published by
:: the Free Software Foundation, either version 3 of the License, or
:: (at your option) any later version.
::
:: This program is distributed in the hope that it will be useful,
:: but WITHOUT ANY WARRANTY; without even the implied warranty of
:: MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
:: GNU Affero General Public License for more details.
::
:: You should have received a copy of the GNU Affero General Public License
:: along with this program.  If not, see <https://www.gnu.org/licenses/>.

SETLOCAL EnableDelayedExpansion

:: --- CONFIGURATION ---
SET REPO_URL=https://github.com/PankajVarma-PUV/SpandaOS.git
SET BRANCH=main

:: Use UTF-8 for better character support in modern CMD/PowerShell
chcp 65001 >nul

echo 🛡️ SpandaOS GitHub Recovery Uploader
echo ---------------------------------------

:: 1. Force Cleanup of any stuck background processes
echo 🧹 Cleaning up stuck Git states...
git rebase --abort >nul 2>&1
git merge --abort >nul 2>&1

:: 2. Ensure we are on a proper branch
git rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel% neq 0 (
    echo 📂 Initializing fresh Git repository...
    git init
    git remote add origin %REPO_URL%
)

:: 3. Remote Verification
echo 🔗 Refreshing GitHub remote link...
git remote set-url origin %REPO_URL%

:: 4. Stage EVERYTHING
echo 🔍 Staging all files...
git add -A

:: 5. Commit with robust quoting
SET /P commit_msg="💬 Enter commit message (or press enter for default): "
if "%commit_msg%"=="" SET commit_msg=Finalized SOTA SpandaOS Architecture

echo 💾 Committing...
git commit -m "%commit_msg%"

:: 6. Handle Branching
echo 🌿 Enforcing branch: %BRANCH%
git branch -M %BRANCH%

:: 7. FORCE SYNC (The Nuclear Option)
echo 🚀 Force-Mirroring local files to GitHub...
echo (This will bypass all "non-fast-forward" errors)
git push -u origin %BRANCH% --force

if %errorlevel% equ 0 (
    echo ---------------------------------------
    echo ✅ SUCCESS! Your entire LOCAL codebase is now live on GitHub.
    echo 🌐 Visit: https://github.com/PankajVarma-PUV/SpandaOS
) else (
    echo -----------------------------------
    echo ❌ FAILED to push. 
    echo Please check your internet connection or GitHub login credentials.
)

pause

