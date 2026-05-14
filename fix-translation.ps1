param(
    [Parameter(Position=0)]
    [string]$InputPath,
    [Parameter(Position=1)]
    [string]$OutputPath,
    [string]$Source = "ja",
    [string]$Target = "id",
    [int]$Batch = 30,
    [switch]$All
)

# Handle POSIX-style --flags passed in $args (unbound arguments)
$raw = $args
$posCandidates = @()
for ($i = 0; $i -lt $raw.Count; $i++) {
    $t = $raw[$i]
    if ($t -like '--*') {
        $opt = $t.TrimStart('-')
        switch ($opt.ToLower()) {
            'source' { if ($i+1 -lt $raw.Count) { $Source = $raw[$i+1]; $i++ } }
            'target' { if ($i+1 -lt $raw.Count) { $Target = $raw[$i+1]; $i++ } }
            'batch' { if ($i+1 -lt $raw.Count) { $Batch = [int]$raw[$i+1]; $i++ } }
            'all' { $All = $true }
            default { }
        }
    } elseif ($t -like '-*') {
        # keep single-dash tokens as positional candidates
        $posCandidates += $t
    } else {
        $posCandidates += $t
    }
}

# If positional params weren't bound, fill them from posCandidates
if (-not $InputPath -and $posCandidates.Count -ge 1) { $InputPath = $posCandidates[0] }
if (-not $OutputPath -and $posCandidates.Count -ge 2) { $OutputPath = $posCandidates[1] }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

if (-not $InputPath) {
    Write-Host "Usage: .\fix-translation.ps1 <input.srt> [output.srt] [-Source <lang>] [-Target <lang>] [--all] [--batch N]"
    exit 2
}

if (-not (Test-Path $InputPath)) {
    Write-Error "Input file '$InputPath' tidak ditemukan."
    exit 1
}

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) { $python = $venvPython } else { $python = "python" }

$argsList = @()
$argsList += $InputPath
$argsList += $OutputPath
$argsList += "--source"
$argsList += $Source
$argsList += "--target"
$argsList += $Target
$argsList += "--batch"
$argsList += $Batch.ToString()
if ($All) { $argsList += "--all" }


Write-Host "▶ Memulai proses terjemahan: $InputPath -> $OutputPath"
& $python (Join-Path $scriptDir "retranslate.py") @argsList
$exit = $LASTEXITCODE
if ($exit -eq 0) { Write-Host "✅ Selesai! File tersimpan di: $OutputPath" } else { Write-Error "ERROR: Script gagal dengan kode $exit" }
exit $exit
