param([int]$Port = 8787)
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output "killing pid $($_.OwningProcess)"
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 800
$root = "c:\Users\User\Desktop\Contact Forms"
$p = Start-Process -FilePath "python" `
    -ArgumentList "-m","uvicorn","gsa_wrap.api:app","--host","127.0.0.1","--port","$Port","--log-level","warning" `
    -WorkingDirectory $root -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput "$root\_work\api.log" -RedirectStandardError "$root\_work\api.err"
Start-Sleep -Seconds 5
if ($p.HasExited) { Write-Output "EXITED"; Get-Content "$root\_work\api.err" -Tail 20 }
else {
    Write-Output "pid=$($p.Id) up"
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$Port/" -TimeoutSec 8
        Write-Output "GET / -> $($r.StatusCode) $($r.RawContentLength) bytes"
        $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 8
        Write-Output "health ok=$($h.ok) app_running=$($h.app_running)"
    } catch { Write-Output "probe err: $_" }
    [IO.File]::WriteAllText("$root\_work\api.pid", $p.Id)
}
