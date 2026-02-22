@echo off
SETLOCAL EnableDelayedExpansion

:: --- CONFIGURATION ---
SET REPO_URL=https://github.com/PankajVarma-PUV/SentinelRAG.git
SET BRANCH=main

:: Use UTF-8 for better character support in modern CMD/PowerShell
chcp 65001 >nul

echo 🛡️ SentinelRAG GitHub Recovery Uploader
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
if "%commit_msg%"=="" SET commit_msg=Finalized SOTA SentinelRAG Architecture

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
    echo 🌐 Visit: https://github.com/PankajVarma-PUV/SentinelRAG
) else (
    echo -----------------------------------
    echo ❌ FAILED to push. 
    echo Please check your internet connection or GitHub login credentials.
)

pause
