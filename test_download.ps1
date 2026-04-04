try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/download?url=https://www.youtube.com/watch?v=jNQXAC9IVRw&format=mp3&quality=192k&title=test" -OutFile "test.mp3"
    Write-Host "Success"
} catch {
    Write-Host "Error occurred:"
    Write-Host $_.Exception.Response
    $stream = $_.Exception.Response.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream)
    $responseBody = $reader.ReadToEnd()
    Write-Host $responseBody
}
