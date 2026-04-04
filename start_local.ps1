Write-Host "Starting FastAPI Backend on port 8000..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; uvicorn main:app --port 8000 --reload"

Write-Host "Starting Frontend Server on port 3000..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; python -m http.server 3000"

Write-Host ""
Write-Host "============================================="
Write-Host "Local DEV environment is running!"
Write-Host "Backend API: http://localhost:8000"
Write-Host "Frontend App: http://localhost:3000"
Write-Host "============================================="
Write-Host "Click the link above to test it in your browser!"
