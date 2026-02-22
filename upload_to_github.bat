@echo off
SETLOCAL EnableDelayedExpansion

:: --- CONFIGURATION ---
SET REPO_URL=https://github.com/PankajVarma-PUV/SentinelRAG.git
SET BRANCH=main

echo 🛡️ SentinelRAG GitHub Uploader
echo -----------------------------------

:: 1. Check if Git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Git is not installed. Please install it from https://git-scm.com/
    pause
    exit /b
)

:: 2. Initialize Git if not already done
if not exist .git (
    echo 📂 Initializing Git repository...
    git init
    git remote add origin %REPO_URL%
) else (
    echo ✅ Git repository already initialized.
    :: Ensure the remote is correct
    git remote set-url origin %REPO_URL%
)

:: 3. Stage changes (respects .gitignore)
echo 🔍 Staging files...
git add .

:: 4. Commit changes
SET /P commit_msg="💬 Enter commit message (or press enter for default): "
if "%commit_msg%"=="" SET commit_msg=feat: Initial commit of SOTA Metacognitive RAG architecture

echo 💾 Committing...
:: Use % instead of ! for the command to avoid CMD expansion issues with quotes
git commit -m "%commit_msg%"

:: 5. Handle Branching
echo 🌿 Setting branch to %BRANCH%...
git branch -M %BRANCH%

:: 6. Sync with Remote (Handles "fetch first" errors)
echo 🔄 Syncing with remote repository...
git pull origin %BRANCH% --rebase --allow-unrelated-histories

:: 7. Push to GitHub
echo 🚀 Pushing to GitHub (%REPO_URL%)...
git push -u origin %BRANCH%

if %errorlevel% equ 0 (
    echo -----------------------------------
    echo ✅ SUCCESS! Code uploaded to GitHub.
    echo 🌐 Visit: %REPO_URL%
) else (
    echo -----------------------------------
    echo ❌ FAILED to push. 
    echo TIP: If this is a new repo, ensure you don't have conflicting files on GitHub.
    echo or try running: git push -u origin %BRANCH% --force
)

pause
