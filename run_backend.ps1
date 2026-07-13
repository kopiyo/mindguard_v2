Set-Location -LiteralPath "C:\Users\apugo\Desktop\mindguard_v2"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
