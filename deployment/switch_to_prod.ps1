# switch_to_prod.ps1
# Switches all APIs from test (dev) to production
# Run this AFTER completing checklist.md

$ErrorActionPreference = "Stop"
$Region = "ap-northeast-1"
$FunctionName = "stock-radio-generator-prod"
$EnvFile = "$PSScriptRoot\.env.prod"

# ── Load .env.prod ────────────────────────────────────────────────────

if (-not (Test-Path $EnvFile)) {
    Write-Host ""
    Write-Host "ERROR: $EnvFile not found." -ForegroundColor Red
    Write-Host "Copy deployment\.env.prod.example to deployment\.env.prod and fill in the values."
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

Write-Host ""
Write-Host "=== Stock Radio: Switch to Production ===" -ForegroundColor Cyan
Write-Host "Function : $FunctionName"
Write-Host "LLM      : $($env_vars['LLM_PROVIDER'])"
Write-Host "TTS      : $($env_vars['TTS_ENGINE'])"
Write-Host ""

$confirm = Read-Host "Proceed? (y/N)"
if ($confirm -ne "y") { Write-Host "Cancelled."; exit 0 }

# ── Step 1: sam build + deploy (prod) ────────────────────────────────

Write-Host ""
Write-Host "[1/3] Building..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot\..\backend"

sam build
if (-not $?) { Write-Host "sam build failed." -ForegroundColor Red; exit 1 }

Write-Host "[2/3] Deploying prod stack..." -ForegroundColor Yellow

$llm    = $env_vars['LLM_PROVIDER']
$tts    = $env_vars['TTS_ENGINE']
$jq     = $env_vars['JQUANTS_API_KEY']
$av     = $env_vars['ALPHA_VANTAGE_API_KEY']
$groq   = $env_vars['GROQ_API_KEY']
$claude = $env_vars['ANTHROPIC_API_KEY']
$openai = $env_vars['OPENAI_API_KEY']

sam deploy --config-env prod `
  --parameter-overrides `
    "Env=prod" `
    "LlmProvider=$llm" `
    "TtsEngine=$tts" `
    "JQuantsApiKey=$jq" `
    "AlphaVantageApiKey=$av" `
    "GroqApiKey=$groq" `
    "AnthropicApiKey=$claude" `
    "OpenAiApiKey=$openai" `
    "GeminiApiKey=skip" `
  --no-confirm-changeset

if (-not $?) { Write-Host "sam deploy failed." -ForegroundColor Red; Pop-Location; exit 1 }
Pop-Location

# ── Step 2: Upload Firebase credentials to SSM ────────────────────────

Write-Host "[3/3] Uploading Firebase credentials to SSM..." -ForegroundColor Yellow

$FirebaseCred = "$PSScriptRoot\firebase-credentials-prod.json"
if (Test-Path $FirebaseCred) {
    $cred = Get-Content $FirebaseCred -Raw -Encoding UTF8
    aws ssm put-parameter `
      --name "/stock-radio/prod/firebase-credentials" `
      --value $cred `
      --type "SecureString" `
      --region $Region `
      --overwrite
    Write-Host "Firebase credentials uploaded." -ForegroundColor Green
} else {
    Write-Host "WARNING: $FirebaseCred not found. Push notifications will not work." -ForegroundColor Yellow
    Write-Host "         Download from Firebase Console and save as deployment\firebase-credentials-prod.json"
}

# ── Done ──────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Production deployment complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Test Lambda manually in AWS Console (prod stack)"
Write-Host "  2. Update iOS APIService.swift baseURL to prod endpoint"
Write-Host "  3. Build iOS app in Xcode and submit to App Store"
Write-Host ""

# Show prod API endpoint
aws cloudformation describe-stacks `
  --stack-name stock-radio-prod `
  --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" `
  --output text `
  --region $Region
