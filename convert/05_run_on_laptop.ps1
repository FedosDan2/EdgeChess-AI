# Transfers only conversion inputs, builds the Linux image, runs FP16 then INT8,
# and downloads results. It does not copy Windows Python or modify host DNS.
param(
    [string]$SshTarget = 'LijnxArcher@192.168.3.11',
    [ValidateSet('fp16', 'int8')][string[]]$Precision = @('fp16', 'int8')
)
$ErrorActionPreference = 'Stop'
$taskArchive = Join-Path $PSScriptRoot 'transfer.tar'
tar -cf $taskArchive -C $PSScriptRoot common.py 04_build_rknn.py Dockerfile requirements-rknn.txt .dockerignore data artifacts/model.json artifacts/pytorch_predictions.json artifacts/yolov8s_split.onnx
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare transfer archive. Run steps 01-03 first.' }
ssh $SshTarget 'mkdir -p edgechess-convert/convert'
if ($LASTEXITCODE -ne 0) { throw 'SSH failed' }
scp $taskArchive "${SshTarget}:edgechess-convert/transfer.tar"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed' }
ssh $SshTarget 'cd edgechess-convert && tar -xf transfer.tar -C convert && docker build -t edgechess-convert:py310 convert'
if ($LASTEXITCODE -ne 0) { throw 'Container build failed; check laptop DNS and docker output' }
foreach ($taskPrecision in $Precision) {
    # Literal Unix substitutions are evaluated by the remote shell only.
    $taskCommand = 'cd edgechess-convert && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp --cpus=2 --memory=5g --memory-swap=7g -v "$PWD/convert:/work/convert" edgechess-convert:py310 04_build_rknn.py --precision ' + $taskPrecision
    ssh $SshTarget $taskCommand
    $taskRunStatus = $LASTEXITCODE
    scp -r "${SshTarget}:edgechess-convert/convert/artifacts/rknn_$taskPrecision" (Join-Path $PSScriptRoot 'artifacts/')
    if ($LASTEXITCODE -ne 0) { throw "Could not retrieve $taskPrecision results" }
    if ($taskRunStatus -ne 0) { throw "$taskPrecision build or verification failed; inspect downloaded logs" }
}
