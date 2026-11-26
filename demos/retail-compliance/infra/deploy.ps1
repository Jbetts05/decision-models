#Requires -Version 7.2
<#
.SYNOPSIS
Deploys the Shelf Check demo to Azure Container Apps, using your existing Foundry Decision-1.1 deployment.

.DESCRIPTION
Creates chargeable resources: Container Apps environment and app, a Basic container
registry, a Log Analytics workspace and a user-assigned managed identity. Grants that
identity a custom role on your Foundry account limited to account read and
decision-model inference. The app is public and anonymous; each process admits at most
-DailyMaxCalls visit requests per UTC day. The count is in memory and resets on restart
or scale-to-zero, so it is an admission limit, not a spend ceiling.
#>
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$Location,
    [Parameter(Mandatory)][string]$FoundryResourceId,
    [Parameter(Mandatory)][string]$DecisionDeployment,
    [int]$DailyMaxCalls = 2000,
    [string]$NamePrefix = 'shelfcheck'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-Location (Split-Path $PSScriptRoot)

if ($FoundryResourceId -notmatch '^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.CognitiveServices/accounts/([^/]+)$') {
    throw 'FoundryResourceId must be the full resource ID of a Microsoft.CognitiveServices account.'
}
$foundrySubscription, $foundryGroup, $foundryName = $Matches[1], $Matches[2], $Matches[3]
if ($foundrySubscription -ne $SubscriptionId) {
    throw 'The Foundry account must be in the same subscription as the deployment (-SubscriptionId).'
}

az account set --subscription $SubscriptionId
$endpoint = az cognitiveservices account show --name $foundryName --resource-group $foundryGroup --query properties.endpoint -o tsv
$deployment = az cognitiveservices account deployment show --name $foundryName --resource-group $foundryGroup `
    --deployment-name $DecisionDeployment --query properties.model.name -o tsv
if ($deployment -notlike 'Microsoft-Decision-1.1*') { throw "Deployment $DecisionDeployment is '$deployment', not Microsoft-Decision-1.1." }

az group create --name $ResourceGroup --location $Location --output none
$common = @('--resource-group', $ResourceGroup, '--template-file', 'infra/main.bicep', '--parameters',
    "namePrefix=$NamePrefix", "foundryAccountName=$foundryName", "foundryResourceGroup=$foundryGroup",
    "foundryEndpoint=$($endpoint.TrimEnd('/'))", "decisionDeployment=$DecisionDeployment", "dailyMaxCalls=$DailyMaxCalls")

Write-Host 'Provisioning registry, identity and environment...'
$registry = az deployment group create @common --query properties.outputs.registryName.value -o tsv

$tag = (Get-Date -Format 'yyyyMMddHHmmss')
Write-Host "Building image shelf-check:$tag in $registry..."
az acr build --registry $registry --image "shelf-check:$tag" . --output none

Write-Host 'Deploying the container app...'
$loginServer = az acr show --name $registry --query loginServer -o tsv
$url = az deployment group create @common "image=$loginServer/shelf-check:$tag" --query properties.outputs.appUrl.value -o tsv

for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        if ((Invoke-RestMethod "$url/healthz" -TimeoutSec 20).status -eq 'ok') { Write-Host "Ready: $url"; exit 0 }
    } catch { Start-Sleep -Seconds 15 }
}
throw "Deployed, but $url/healthz did not respond. Check the container app logs."
