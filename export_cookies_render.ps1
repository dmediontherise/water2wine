<#
.SYNOPSIS
    Exports YouTube cookies from your browser and sets them up for Render.

.DESCRIPTION
    Uses yt-dlp to pull cookies from Chrome/Edge/Brave/Firefox, filters to
    YouTube domains only, copies the value to your clipboard, and optionally
    calls the Render API directly if you supply -RenderApiKey and -RenderServiceId.

    IMPORTANT: Close the target browser completely before running.
    Chrome/Edge/Brave lock the cookie database while the browser is open.

.EXAMPLE
    .\export_cookies_render.ps1
    .\export_cookies_render.ps1 -Browser edge
    .\export_cookies_render.ps1 -RenderApiKey "rnd_xxxx" -RenderServiceId "srv-xxxx"
#>

param(
    [string]$Browser = "",
    [string]$RenderApiKey = $env:RENDER_API_KEY,
    [string]$RenderServiceId = $env:RENDER_SERVICE_ID
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  water2wine: YouTube Cookie Exporter for Render" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Locate yt-dlp
$ytdlpAvail = Get-Command yt-dlp -ErrorAction SilentlyContinue
if (-not $ytdlpAvail) {
    Write-Host "ERROR: yt-dlp not found. Run: pip install yt-dlp" -ForegroundColor Red
    exit 1
}

$outFile = Join-Path $PSScriptRoot "youtube_cookies_export.txt"
$testUrl = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

$browsers = if ($Browser) { @($Browser) } else { @("chrome", "edge", "brave", "firefox", "opera", "vivaldi") }

Write-Host "STEP 1: Close your browser completely before proceeding." -ForegroundColor Yellow
Write-Host "        Chrome/Edge/Brave lock the cookie DB while open." -ForegroundColor Yellow
Write-Host ""
Read-Host "  Press Enter when browser is closed (Ctrl+C to cancel)"
Write-Host ""

$success = $false
foreach ($b in $browsers) {
    Write-Host "  Trying $b..." -NoNewline
    try {
        $result = & yt-dlp --cookies-from-browser $b --cookies $outFile --skip-download --quiet $testUrl 2>&1
        if ($LASTEXITCODE -eq 0 -and (Test-Path $outFile) -and (Get-Item $outFile).Length -gt 100) {
            Write-Host " OK" -ForegroundColor Green
            $success = $true
            break
        }
    } catch { }
    Write-Host " failed" -ForegroundColor DarkGray
}

if (-not $success) {
    Write-Host ""
    Write-Host "ERROR: Could not extract cookies from any browser." -ForegroundColor Red
    Write-Host "Make sure you are logged into YouTube and the browser is fully closed." -ForegroundColor Yellow
    Write-Host "Try:  .\export_cookies_render.ps1 -Browser firefox" -ForegroundColor Cyan
    exit 1
}

# Filter to YouTube-related domains only (keeps the value compact)
$lines = Get-Content $outFile
$header = $lines | Where-Object { $_ -match "^#" }
$ytLines = $lines | Where-Object { $_ -match "\.(youtube|googlevideo|ytimg|ggpht|google)\." -and $_ -notmatch "^#" }
if ($ytLines.Count -ge 3) {
    $filtered = ($header + $ytLines) -join "`n"
    Write-Host "  Exported $($ytLines.Count) YouTube cookies." -ForegroundColor Green
} else {
    $filtered = (Get-Content $outFile -Raw)
    Write-Host "  Exported full cookie file ($($lines.Count) lines)." -ForegroundColor Green
}

Set-Content -Path $outFile -Value $filtered -Encoding UTF8
$filtered | Set-Clipboard
Write-Host "  Saved to: $outFile"
Write-Host "  Value copied to clipboard." -ForegroundColor Green

# Optional: set via Render API automatically
if ($RenderApiKey -and $RenderServiceId) {
    Write-Host ""
    Write-Host "STEP 2: Setting YOUTUBE_COOKIES via Render API..." -NoNewline
    $body = @{ envVars = @(@{ key = "YOUTUBE_COOKIES"; value = $filtered }) } | ConvertTo-Json -Depth 5
    try {
        Invoke-RestMethod `
            -Uri "https://api.render.com/v1/services/$RenderServiceId/env-vars" `
            -Method PUT `
            -Headers @{ Authorization = "Bearer $RenderApiKey"; "Content-Type" = "application/json" } `
            -Body $body | Out-Null
        Write-Host " Done!" -ForegroundColor Green
        Write-Host "Render will redeploy automatically." -ForegroundColor Cyan
    } catch {
        Write-Host " FAILED: $_" -ForegroundColor Red
        Write-Host "Fall back to the manual steps below." -ForegroundColor Yellow
        $RenderApiKey = ""
    }
}

if (-not $RenderApiKey -or -not $RenderServiceId) {
    Write-Host ""
    Write-Host "STEP 2: Paste into Render manually:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. Go to  https://dashboard.render.com"
    Write-Host "  2. Open your youtube-converter-api service"
    Write-Host "  3. Click  Environment > Environment Variables"
    Write-Host "  4. Add variable:"
    Write-Host "       Key   ->  YOUTUBE_COOKIES"
    Write-Host "       Value ->  (paste from clipboard - already copied)"
    Write-Host "  5. Click Save Changes"
    Write-Host "     Render will trigger a redeploy automatically."
    Write-Host ""
    Write-Host "  Tip: to skip this next time, run:" -ForegroundColor DarkGray
    Write-Host "    .\export_cookies_render.ps1 -RenderApiKey rnd_xxx -RenderServiceId srv_xxx" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Cookies expire in approx 1-2 weeks. Re-run when 429 errors return." -ForegroundColor Yellow
Write-Host ""
