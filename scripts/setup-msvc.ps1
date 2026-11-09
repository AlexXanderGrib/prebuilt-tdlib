param(
    [Parameter(Mandatory)]
    [ValidateSet('x86', 'x64')]
    [string]$Architecture
)

$ErrorActionPreference = 'Stop'
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or !$installation) {
    throw 'Cannot find the Visual Studio C++ toolchain.'
}

# Keep the compiler host 64-bit even when targeting an x86 DLL. Import the
# developer prompt's environment into subsequent GitHub Actions steps.
$command = "`"$installation\Common7\Tools\VsDevCmd.bat`" -no_logo -arch=$Architecture -host_arch=x64 >nul && set"
$variables = & $env:ComSpec /d /s /c "`"$command`""
if ($LASTEXITCODE -ne 0) {
    throw 'Visual Studio developer environment setup failed.'
}
foreach ($variable in $variables) {
    if ($variable -match '^([^=]+)=(.*)$') {
        $name, $value = $Matches[1], $Matches[2]
        if ($name -notmatch '^(GITHUB_|RUNNER_)' -and
            [Environment]::GetEnvironmentVariable($name, 'Process') -cne $value) {
            "$name=$value" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
        }
    }
}
