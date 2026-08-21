# deploy_dev.ps1
# Reads API keys from .env and deploys to dev environment

$EnvFile = Join-Path $PSScriptRoot "..\.env"

if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: .env file not found at $EnvFile" -ForegroundColor Red
    exit 1
}

$env_vars = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $parts = $line -split "=", 2
        if ($parts.Length -eq 2) {
            $env_vars[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
}

$groq = $env_vars['GROQ_API_KEY']
$av   = $env_vars['ALPHA_VANTAGE_API_KEY']
$fh   = $env_vars['FINNHUB_API_KEY']
$ant  = $env_vars['ANTHROPIC_API_KEY']

if (-not $groq -or -not $av -or -not $fh) {
    Write-Host "ERROR: Missing keys in .env (need GROQ_API_KEY, ALPHA_VANTAGE_API_KEY, FINNHUB_API_KEY)" -ForegroundColor Red
    exit 1
}
if (-not $ant) { $ant = "skip" }

Write-Host "=== Dev Deploy Start ===" -ForegroundColor Cyan

Push-Location (Join-Path $PSScriptRoot "..\backend")

sam build
if (-not $?) {
    Write-Host "sam build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}

sam deploy `
  --config-env dev `
  --stack-name stock-radio-dev `
  --region ap-northeast-1 `
  --capabilities CAPABILITY_IAM `
  --resolve-s3 `
  --parameter-overrides `
    "Env=dev" `
    "LlmProvider=groq" `
    "TtsEngine=standard" `
    "GroqApiKey=$groq" `
    "AlphaVantageApiKey=$av" `
    "FinnhubApiKey=$fh" `
    "AnthropicApiKey=$ant" `
  --no-confirm-changeset

Pop-Location
Write-Host "=== Deploy Complete ===" -ForegroundColor Green
