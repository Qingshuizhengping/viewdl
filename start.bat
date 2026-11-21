@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo [ViewDL] first run: creating venv and installing dependencies...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo [ViewDL] starting at http://127.0.0.1:8770  (Ctrl+C to stop)
.venv\Scripts\python.exe app.py
pause
