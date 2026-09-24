param(
    [Parameter(Mandatory = $true)]
    [string]$CandidateInstaller,

    [Parameter(Mandatory = $true)]
    [string]$Repository,

    [Parameter(Mandatory = $true)]
    [string]$WorkRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest


function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @(),

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    Write-Host "Starting: $Description"
    $process = Start-Process -FilePath $FilePath `
        -ArgumentList $Arguments `
        -Wait `
        -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$Description exited with code $($process.ExitCode)"
    }
}


function Show-DiagnosticLog {
    param([string]$LogPath)

    if (Test-Path $LogPath) {
        Write-Host "Application diagnostic log:"
        Get-Content $LogPath
    }
    else {
        Write-Host "No application diagnostic log was created at $LogPath"
    }
}


function Invoke-InstalledVerification {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallDir,

        [Parameter(Mandatory = $true)]
        [string]$VerificationDir,

        [Parameter(Mandatory = $true)]
        [string]$HfHome
    )

    $app = Join-Path $InstallDir "medical-redactor.exe"
    $logPath = Join-Path $InstallDir "logs\medical-redactor.log"
    if (-not (Test-Path $app)) {
        throw "Installed executable is missing: $app"
    }

    $previousHfHome = $env:HF_HOME
    $env:HF_HOME = $HfHome
    try {
        Invoke-CheckedProcess `
            -FilePath $app `
            -Arguments @("--release-verify", "`"$VerificationDir`"") `
            -Description "Installed application release verification"
    }
    catch {
        Show-DiagnosticLog -LogPath $logPath
        throw
    }
    finally {
        $env:HF_HOME = $previousHfHome
    }

    $marker = Join-Path $VerificationDir "release-verification.json"
    if (-not (Test-Path $marker)) {
        Show-DiagnosticLog -LogPath $logPath
        throw "Installed verification did not create its completion marker: $marker"
    }

    $outputs = Get-ChildItem (Join-Path $VerificationDir "output") -Filter "*.md"
    if ($outputs.Count -ne 2) {
        Show-DiagnosticLog -LogPath $logPath
        throw "Installed verification produced $($outputs.Count) Markdown files instead of 2"
    }
}


function Install-Silently {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Installer,

        [string]$InstallDir
    )

    $arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    if ($InstallDir) {
        $arguments += "/DIR=`"$InstallDir`""
    }
    Invoke-CheckedProcess `
        -FilePath $Installer `
        -Arguments $arguments `
        -Description "Installer $([IO.Path]::GetFileName($Installer))"
}


function Get-PreviousInstaller {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repo,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $headers = @{
        "Accept" = "application/vnd.github+json"
        "User-Agent" = "medical-redactor-release-verifier"
    }
    if ($env:GITHUB_TOKEN) {
        $headers["Authorization"] = "Bearer $($env:GITHUB_TOKEN)"
    }

    $release = Invoke-RestMethod `
        -Uri "https://api.github.com/repos/$Repo/releases/latest" `
        -Headers $headers
    $asset = $release.assets |
        Where-Object { $_.name -like "*-setup.exe" } |
        Select-Object -First 1
    if (-not $asset) {
        throw "The latest published release has no *-setup.exe asset"
    }

    Write-Host "Downloading previous installer $($asset.name)"
    Invoke-WebRequest `
        -Uri $asset.browser_download_url `
        -Headers $headers `
        -OutFile $Destination
}


$candidate = (Resolve-Path $CandidateInstaller).Path
$root = [IO.Path]::GetFullPath($WorkRoot)
New-Item -ItemType Directory -Force $root | Out-Null
$hfHome = Join-Path $root "hf-cache"

# First prove a fresh candidate installation with no app models and an empty
# Docling cache. This exercises downloads, vector PDF conversion, OCR, NER,
# output writing, Unicode paths, and the real Qt Windows platform plugin.
$freshInstall = Join-Path $root "fresh-install"
Install-Silently -Installer $candidate -InstallDir $freshInstall
Invoke-InstalledVerification `
    -InstallDir $freshInstall `
    -VerificationDir (Join-Path $root "fresh-verification") `
    -HfHome $hfHome

$verifiedModels = Join-Path $root "verified-models"
Copy-Item `
    -Path (Join-Path $freshInstall "models") `
    -Destination $verifiedModels `
    -Recurse

# Remove the fresh custom installation so its Inno Setup registration cannot
# redirect the previous-version installation away from the normal directory.
$freshUninstaller = Join-Path $freshInstall "unins000.exe"
Invoke-CheckedProcess `
    -FilePath $freshUninstaller `
    -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
    -Description "Fresh candidate uninstaller"

# Install the previously published version, add real models plus preservation
# sentinels, then install the candidate over it at the normal per-user path.
$previousInstaller = Join-Path $root "previous-windows-setup.exe"
Get-PreviousInstaller -Repo $Repository -Destination $previousInstaller
Install-Silently -Installer $previousInstaller

$defaultInstall = Join-Path $env:LOCALAPPDATA "Programs\Medical Redactor"
$modelsDir = Join-Path $defaultInstall "models"
$logsDir = Join-Path $defaultInstall "logs"
$staleRuntime = Join-Path $defaultInstall "_internal\stale-runtime-file.txt"
New-Item -ItemType Directory -Force $modelsDir | Out-Null
New-Item -ItemType Directory -Force $logsDir | Out-Null
New-Item -ItemType Directory -Force (Split-Path $staleRuntime) | Out-Null
Copy-Item -Path (Join-Path $verifiedModels "*") -Destination $modelsDir -Recurse -Force
Set-Content (Join-Path $modelsDir "preserve-models.txt") "preserve models"
Set-Content (Join-Path $logsDir "preserve-logs.txt") "preserve logs"
Set-Content $staleRuntime "old runtime"

Install-Silently -Installer $candidate

if (Test-Path $staleRuntime) {
    throw "Candidate upgrade did not replace the previous _internal runtime tree"
}
if (-not (Test-Path (Join-Path $modelsDir "preserve-models.txt"))) {
    throw "Candidate upgrade removed the existing models directory"
}
if (-not (Test-Path (Join-Path $logsDir "preserve-logs.txt"))) {
    throw "Candidate upgrade removed the existing logs directory"
}

Invoke-InstalledVerification `
    -InstallDir $defaultInstall `
    -VerificationDir (Join-Path $root "upgrade-verification") `
    -HfHome $hfHome

# The uninstall prompt defaults to removing models. Silent uninstall suppresses
# the prompt and selects that default. Prove both current and legacy model
# locations are deleted while diagnostic logs remain available.
$legacyModelsDir = Join-Path $env:LOCALAPPDATA "medical-redactor\models"
New-Item -ItemType Directory -Force $legacyModelsDir | Out-Null
Set-Content (Join-Path $legacyModelsDir "legacy-model.txt") "legacy model"

$finalUninstaller = Join-Path $defaultInstall "unins000.exe"
Invoke-CheckedProcess `
    -FilePath $finalUninstaller `
    -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
    -Description "Final candidate uninstaller"

if (Test-Path $modelsDir) {
    throw "Candidate uninstaller left downloaded models behind"
}
if (Test-Path $legacyModelsDir) {
    throw "Candidate uninstaller left legacy downloaded models behind"
}
if (-not (Test-Path (Join-Path $logsDir "preserve-logs.txt"))) {
    throw "Candidate uninstaller unexpectedly removed diagnostic logs"
}

Write-Host "Windows fresh-install, upgrade, and model-removing uninstall verification passed"
