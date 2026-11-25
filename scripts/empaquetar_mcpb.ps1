# Construye la extensión con las dependencias de producción fijadas en uv.lock.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $repo 'dist'
$staging = Join-Path $dist ('mcpb-' + [guid]::NewGuid())
$bundle = Join-Path $dist 'solidedge-cli.mcpb'

New-Item -ItemType Directory -Path $staging -Force | Out-Null
try {
    $manifest = Join-Path $staging 'manifest.json'
    $server = Join-Path $staging 'server'
    $lib = Join-Path $server 'lib'
    $requirements = Join-Path $staging 'requirements.txt'
    New-Item -ItemType Directory -Path $lib | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo 'mcpb/manifest.json'), (Join-Path $repo 'mcpb/README.md'), (Join-Path $repo 'LICENSE') -Destination $staging
    Copy-Item -LiteralPath (Join-Path $repo 'mcpb/server/main.py') -Destination $server

    uv export --project $repo --locked --no-default-groups --extra mcp --no-emit-project --format requirements-txt --output-file $requirements --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Falló uv export.' }
    uv pip install --target $lib --python-version 3.11 --python-platform x86_64-pc-windows-msvc --only-binary ':all:' --no-deps -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias.' }
    Copy-Item -LiteralPath (Join-Path $repo 'src/se_cli') -Destination $lib -Recurse
    @('**/__pycache__/', '**/*.pyc', '**/bin/') | Set-Content (Join-Path $staging '.mcpbignore')

    $mcpbHelp = npx -y @anthropic-ai/mcpb --help
    if ($LASTEXITCODE -ne 0) { throw 'Falló mcpb --help.' }
    if ($mcpbHelp -match '^\s+validate\s') {
        npx -y @anthropic-ai/mcpb validate $manifest
        if ($LASTEXITCODE -ne 0) { throw 'El manifiesto MCPB no es válido.' }
    }
    npx -y @anthropic-ai/mcpb pack $staging $bundle
    if ($LASTEXITCODE -ne 0) { throw 'Falló mcpb pack.' }
}
finally {
    $resolved = (Resolve-Path -LiteralPath $staging).Path
    $distPrefix = (Resolve-Path -LiteralPath $dist).Path + [IO.Path]::DirectorySeparatorChar
    if ($resolved.StartsWith($distPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

