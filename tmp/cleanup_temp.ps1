# Cleanup temp files from repo root
$files = Get-ChildItem -Path . -File | Where-Object { $_.Name -match '^\.tmp_|^_run_|^\.commit_msg' }
foreach ($f in $files) {
    Move-Item -Path $f.FullName -Destination '.backup\' -Force
    Write-Host ("Moved: " + $f.Name)
}
Write-Host ("Total: " + $files.Count + " files moved")
