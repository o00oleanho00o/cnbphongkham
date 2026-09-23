$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
  flutter pub get
  if ($LASTEXITCODE -ne 0) { throw 'flutter pub get failed' }
  dart run build_runner build
  if ($LASTEXITCODE -ne 0) { throw 'build_runner failed' }
  flutter build web --base-href /native-preview/ --no-web-resources-cdn
  if ($LASTEXITCODE -ne 0) { throw 'flutter build web failed' }
  $previewTarget = Join-Path $PSScriptRoot '../prototype/native-preview'
  New-Item -ItemType Directory -Force $previewTarget | Out-Null
  Copy-Item 'build/web/*' $previewTarget -Recurse -Force
  Write-Output 'Preview: http://127.0.0.1:4173/native-review/'
} finally { Pop-Location }
