# Creates an isolated CPU environment. Run from any directory with uv installed.
$ErrorActionPreference = 'Stop'
$taskPython = '3.10'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.python'
$taskVenv = Join-Path $PSScriptRoot '.venv'
$taskCache = Join-Path $PSScriptRoot '.cache'
if (Test-Path "$taskVenv/Scripts/python.exe") {
    $taskVersion = & "$taskVenv/Scripts/python.exe" -c 'import sys; print("%s.%s" % sys.version_info[:2])'
    if ($taskVersion -ne $taskPython) { throw "Existing venv uses Python $taskVersion; recreate it with Python $taskPython" }
}
if (-not (Test-Path "$taskVenv/Scripts/python.exe")) {
    uv venv $taskVenv --python $taskPython --cache-dir $taskCache
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment' }
}
uv pip install --python "$taskVenv/Scripts/python.exe" --cache-dir $taskCache torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Cannot install PyTorch CPU' }
uv pip install --python "$taskVenv/Scripts/python.exe" --cache-dir $taskCache -r "$PSScriptRoot/requirements-local.txt"
if ($LASTEXITCODE -ne 0) { throw 'Cannot install conversion dependencies' }
