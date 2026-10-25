# Gets a Windows computer ready for last-job-search, with no administrator and no winget.
# COMPUTER.md has Claude run it from the Claude desktop app's first chat on the computer,
# where the only shell may be Windows PowerShell 5.1 and nothing else is installed:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File computer_setup.ps1
#
# It installs only what is missing, each into the person's own folders:
#   Git      PortableGit, the portable build of Git for Windows, into
#            %LOCALAPPDATA%\Programs\PortableGit, put on
#            the user PATH, and Claude Code told where its bash.exe is
#            (CLAUDE_CODE_GIT_BASH_PATH in %USERPROFILE%\.claude\settings.json, the setting
#            code.claude.com/docs/en/setup gives for a Git Bash it cannot find).
#   Python   the Python install manager from python.org (docs.python.org/3/using/windows),
#            added with Add-AppxPackage as its page says, then the newest Python. It gives
#            the python, py and python3 commands.
#   gh       GitHub's command line from its release zip, into %LOCALAPPDATA%\Programs\gh.
# One line per thing, then "READY" and the paths a chat that started before them uses.
# Exit 0 when everything is there, 1 when something is not (the line says what to do).

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'      # Windows PowerShell 5.1 downloads crawl with it
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Programs = Join-Path $env:LOCALAPPDATA 'Programs'
$Work = Join-Path $env:TEMP ('ljs_setup_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$GhFallback = '2.103.2'
$GitFallback = '2.56.0'
$Failed = @()
$Restart = $false

function Say([string]$what, [string]$said) { Write-Output ($what + ': ' + $said) }

function Add-UserPath([string]$dir, [switch]$Front) {
    $now = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($now) { $parts = $now.Split(';') | Where-Object { $_ } }
    if ($parts | Where-Object { $_.TrimEnd('\') -ieq $dir.TrimEnd('\') }) { return }
    if ($Front) { $parts = @($dir) + $parts } else { $parts = $parts + @($dir) }
    [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
    $env:Path = $dir + ';' + $env:Path
}

function Get-File([string]$url, [string]$dest) {
    # curl.exe ships with Windows 10 and 11 and is far faster than Invoke-WebRequest in 5.1.
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -fsSL --retry 3 -o $dest $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $dest)) { return }
    }
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
}

function Get-Latest([string]$repo, [string]$fallback, [string]$strip) {
    # The newest release, from where its page redirects: no API, no rate limit.
    $loc = ''
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        $loc = & curl.exe -sS -o NUL -m 20 -w '%{redirect_url}' ('https://github.com/' + $repo + '/releases/latest')
    }
    if ($loc -match '/tag/([^/?#]+)$') { return ($Matches[1] -replace $strip, '') }
    return $fallback
}

function Set-ClaudeEnv([string]$name, [string]$value) {
    $dir = Join-Path $env:USERPROFILE '.claude'
    $path = Join-Path $dir 'settings.json'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $data = New-Object PSObject
    if (Test-Path $path) {
        try { $data = Get-Content -Raw -Path $path | ConvertFrom-Json } catch { return $false }
        if ($null -eq $data) { $data = New-Object PSObject }
    }
    if (-not ($data.PSObject.Properties.Name -contains 'env')) {
        $data | Add-Member -NotePropertyName 'env' -NotePropertyValue (New-Object PSObject)
    }
    if ($data.env.PSObject.Properties.Name -contains $name) { $data.env.$name = $value }
    else { $data.env | Add-Member -NotePropertyName $name -NotePropertyValue $value }
    # UTF-8 without a byte-order mark, which every JSON reader accepts.
    [IO.File]::WriteAllText($path, ($data | ConvertTo-Json -Depth 20), ([Text.UTF8Encoding]::new($false)))
    return $true
}

# ------------------------------------------------------------------ Git
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    Say 'Git' 'already here'
} else {
    try {
        $v = Get-Latest 'git-for-windows/git' $GitFallback '^v|\.windows\.\d+$'
        $arch = '64-bit'
        if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'arm64' }
        $name = 'PortableGit-' + $v + '-' + $arch + '.7z.exe'
        $exe = Join-Path $Work $name
        Get-File ('https://github.com/git-for-windows/git/releases/download/v' + $v + '.windows.1/' + $name) $exe
        $dest = Join-Path $Programs 'PortableGit'
        $bash = Join-Path $dest 'bin\bash.exe'
        foreach ($try in @(@(('-o' + $dest), '-y'), @('-y', '-gm2', ('-InstallPath=' + $dest)))) {
            Start-Process -FilePath $exe -ArgumentList $try -Wait -NoNewWindow
            for ($i = 0; $i -lt 60 -and -not (Test-Path (Join-Path $dest 'cmd\git.exe')); $i++) { Start-Sleep -Seconds 1 }
            if (Test-Path $bash) { break }
        }
        if (-not (Test-Path $bash)) { throw 'it would not unpack' }
        Add-UserPath (Join-Path $dest 'cmd')
        $told = Set-ClaudeEnv 'CLAUDE_CODE_GIT_BASH_PATH' $bash
        $Restart = $true
        if ($told) { Say 'Git' ('installed (' + $v + '), in your own folder') }
        else { Say 'Git' ('installed; add CLAUDE_CODE_GIT_BASH_PATH=' + $bash + ' to your Claude settings') }
    } catch {
        $Failed += 'Git'
        Say 'Git' ('did not install: ' + $_.Exception.Message + '. Check this computer is online, then run this again')
    }
}

# ------------------------------------------------------------------ Python
function Find-Python {
    foreach ($c in @(@('python3'), @('python'), @('py', '-3'))) {
        $cmd = Get-Command $c[0] -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $rest = @()
        if ($c.Count -gt 1) { $rest = $c[1..($c.Count - 1)] }
        try {
            $out = & $cmd.Source @rest -c 'import sys; print(sys.version_info >= (3, 9)); print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $out -and ($out[0] -eq 'True')) { return $out[1] }
        } catch { }
    }
    return $null
}
$py = Find-Python
if ($py) {
    Say 'Python' ('already here (' + $py + ')')
} else {
    try {
        $index = (& curl.exe -fsSL 'https://www.python.org/ftp/python/pymanager/') -join "`n"
        $versions = [regex]::Matches($index, 'python-manager-(\d+)\.(\d+)\.msix"') |
            ForEach-Object { [version]($_.Groups[1].Value + '.' + $_.Groups[2].Value) } | Sort-Object -Descending
        if (-not $versions) { throw 'python.org listed no install manager' }
        $msix = Join-Path $Work 'python-manager.msix'
        Get-File ('https://www.python.org/ftp/python/pymanager/python-manager-' + $versions[0].ToString() + '.msix') $msix
        Add-AppxPackage -Path $msix
        $env:Path = (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps') + ';' + $env:Path
        & pymanager install --configure -y | Out-Null
        & pymanager install default | Out-Null
        $py = Find-Python
        if (-not $py) { throw 'it installed, but no python command answers yet' }
        Say 'Python' ('installed (' + $py + ')')
    } catch {
        $Failed += 'Python'
        Say 'Python' ('did not install: ' + $_.Exception.Message + '. The installer at https://www.python.org/downloads/ works too (tick "Add python.exe to PATH")')
    }
}

# ------------------------------------------------------------------ gh
$gh = Get-Command gh -ErrorAction SilentlyContinue
$ghExe = ''
if ($gh) {
    $ghExe = $gh.Source
    Say "GitHub's command line" 'already here'
} else {
    try {
        $v = Get-Latest 'cli/cli' $GhFallback '^v'
        $arch = 'amd64'
        if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'arm64' }
        $zip = Join-Path $Work ('gh_' + $v + '_windows_' + $arch + '.zip')
        Get-File ('https://github.com/cli/cli/releases/download/v' + $v + '/gh_' + $v + '_windows_' + $arch + '.zip') $zip
        $dest = Join-Path $Programs 'gh'
        Expand-Archive -Path $zip -DestinationPath $dest -Force
        $ghExe = Join-Path $dest 'bin\gh.exe'
        if (-not (Test-Path $ghExe)) { throw 'the zip had no gh.exe' }
        Add-UserPath (Join-Path $dest 'bin')
        Say "GitHub's command line" ('installed (' + $v + ')')
    } catch {
        $Failed += "GitHub's command line"
        Say "GitHub's command line" ('did not install: ' + $_.Exception.Message)
    }
}

Remove-Item -Recurse -Force -Path $Work -ErrorAction SilentlyContinue
if ($Failed.Count -gt 0) {
    Write-Output ('NOT READY: ' + ($Failed -join ', '))
    exit 1
}
Write-Output 'READY'
$g = Get-Command git -ErrorAction SilentlyContinue
if ($g) { Write-Output ('git: ' + $g.Source) }
if ($py) { Write-Output ('python: ' + $py) }
if ($ghExe) { Write-Output ('gh: ' + $ghExe) }
if ($Restart) { Write-Output 'restart: the Claude app, once, so new chats use the Git it installed' }
exit 0
