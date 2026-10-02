@echo off
REM ============================================================
REM  WhaleTrace — live smart-money monitor
REM  Polls wallets in watchlist.txt, alerts on new buys.
REM  Optional Telegram: set both vars below (or remove to console-only)
REM ============================================================
cd /d "%~dp0"

REM Telegram bot token + chat id (optional — get from @BotFather)
if "%TG_BOT_TOKEN%"=="" set TG_BOT_TOKEN=
if "%TG_CHAT_ID%"=="" set TG_CHAT_ID=

echo === WhaleTrace monitor running ===
echo Polling watchlist.txt every 5 minutes. Ctrl+C to stop.
python watch.py --interval 300

pause
