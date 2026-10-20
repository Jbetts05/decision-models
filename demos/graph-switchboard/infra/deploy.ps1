#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [string]$Location = 'swedencentral',
    [string[]]$DatabaseRegions = @('northeurope', 'westeurope', 'uksouth'),
    [string]$ResourceGroup = 'rg-graph-switchboard',
    [Parameter(Mandatory)][string]$FoundryResourceGroup,
    [Parameter(Mandatory)][string]$FoundryAccount,
    [string]$ConfigPath = 'config.local.json',
    [switch]$ValidateOnly,
    [switch]$SkipFoundation
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path $PSScriptRoot -Parent

function Invoke-Azure {
    param([string[]]$Arguments)
    $errorPath = Join-Path $root '.azure\cli-error.local.txt'
    $output = & az @Arguments --subscription $SubscriptionId --only-show-errors 2> $errorPath
    if ($LASTEXITCODE -ne 0) {
        $details = Get-Content -LiteralPath $errorPath -Raw
        [Console]::Error.WriteLine($details)
        $failure = [InvalidOperationException]::new(
            "Azure CLI failed: $($Arguments[0..([Math]::Min(2, $Arguments.Length - 1))] -join ' ')")
        $failure.Data['AzureDetails'] = $details
        throw $failure
    }
    return $output
}

function Invoke-AzureJson {
    param([string[]]$Arguments)
    $text = (Invoke-Azure ($Arguments + @('--output', 'json'))) -join "`n"
    return $text | ConvertFrom-Json -AsHashtable
}

function Write-Parameters {
    param([string]$Name, [hashtable]$Values)
    $parameters = @{}
    foreach ($key in $Values.Keys) { $parameters[$key] = @{ value = $Values[$key] } }
    $path = Join-Path $root ".azure\$Name.parameters.local.json"
    @{
        '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
        contentVersion = '1.0.0.0'
        parameters = $parameters
    } | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $path -Encoding utf8
    return $path
}

function Wait-Healthy {
    param([string]$Origin)
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        $response = Invoke-WebRequest "$Origin/health/ready" -SkipHttpErrorCheck -TimeoutSec 15
        if ($response.StatusCode -eq 200) { return }
        if ($response.StatusCode -notin @(404, 502, 503)) {
            throw "Readiness returned HTTP $($response.StatusCode)."
        }
        Start-Sleep -Seconds 5
    }
    throw 'The deployed service did not become ready.'
}

Push-Location $root
try {
    $null = New-Item -ItemType Directory -Path '.azure' -Force
    $account = Invoke-AzureJson @('account', 'show')
    if ($account.id -ne $SubscriptionId) { throw 'Unexpected Azure subscription.' }
    if (-not $DatabaseRegions.Count) { throw 'At least one approved database region is required.' }
    $groupExists = Invoke-AzureJson @('group', 'exists', '--name', $ResourceGroup)
    if ($groupExists) {
        $existingDatabases = @(Invoke-AzureJson @('resource', 'list', '--resource-group', $ResourceGroup,
            '--resource-type', 'Microsoft.DBforPostgreSQL/flexibleServers'))
        if ($existingDatabases.Count -gt 1) { throw 'Multiple database servers require explicit selection.' }
        if ($existingDatabases.Count -eq 1) {
            if ($existingDatabases[0].location -notin $DatabaseRegions) {
                throw 'Existing database region is outside the supplied approved region list.'
            }
            $DatabaseRegions = @($existingDatabases[0].location)
            Write-Output "Reusing database region $($DatabaseRegions[0])."
        }
    }

    foreach ($file in @('subscription', 'application', 'foundry-access')) {
        & az bicep build --file ".\infra\$file.bicep" --stdout > $null
        if ($LASTEXITCODE -ne 0) { throw "Bicep compilation failed: $file" }
    }
    $python = if ($IsWindows) { '.\.venv\Scripts\python.exe' } else { './.venv/bin/python' }
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Create this demo''s .venv before deployment; dependencies are never installed globally.'
    }
    & $python -m pip download --quiet --only-binary=:all: --implementation cp --python-version 3.13 `
        --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 `
        --dest '.\.venv\wheelhouse' -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Linux dependency wheel download failed.' }

    $secretPath = Join-Path $root '.azure\deployment-secrets.clixml'
    if (Test-Path -LiteralPath $secretPath) {
        if (-not $IsWindows) { throw 'Use explicit environment credentials outside Windows.' }
        $secrets = Import-Clixml -LiteralPath $secretPath
        $adminPassword = [Net.NetworkCredential]::new('', $secrets.Admin).Password
        $appPassword = [Net.NetworkCredential]::new('', $secrets.Application).Password
    } elseif ($env:GRAPH_ADMIN_PASSWORD -and $env:GRAPH_APP_PASSWORD) {
        $adminPassword = $env:GRAPH_ADMIN_PASSWORD
        $appPassword = $env:GRAPH_APP_PASSWORD
    } else {
        if (-not $IsWindows) {
            throw 'Set GRAPH_ADMIN_PASSWORD and GRAPH_APP_PASSWORD to stable secret values.'
        }
        $adminPassword = 'Aa1-' + [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
        $appPassword = 'Aa1-' + [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
        @{
            Admin = ConvertTo-SecureString $adminPassword -AsPlainText -Force
            Application = ConvertTo-SecureString $appPassword -AsPlainText -Force
        } | Export-Clixml -LiteralPath $secretPath
    }

    $foundationParameters = Write-Parameters 'foundation' @{
        location = $Location
        databaseLocation = $DatabaseRegions[0]
        resourceGroupName = $ResourceGroup
        administratorPassword = $adminPassword
        applicationPassword = $appPassword
    }
    try {
        if ($ValidateOnly) {
            Invoke-Azure @('deployment', 'sub', 'validate', '--name', 'graph-switchboard-preflight',
                '--location', $Location, '--template-file', '.\infra\subscription.bicep',
                '--parameters', "@$foundationParameters", '--output', 'none')
            Write-Output 'ARM provider validation passed.'
            $preview = Invoke-AzureJson @('deployment', 'sub', 'what-if',
                '--name', 'graph-switchboard-preflight', '--location', $Location,
                '--template-file', '.\infra\subscription.bicep',
                '--parameters', "@$foundationParameters", '--no-pretty-print')
            if ($preview.changes | Where-Object { $_.changeType -eq 'Delete' }) {
                throw 'What-if includes deletion; obtain explicit approval before continuing.'
            }
            $preview | ConvertTo-Json -Depth 100 | Set-Content '.azure\preview.local.json'
            Write-Output 'ARM what-if and policy validation passed; no deletions.'
            return
        }

        if ($SkipFoundation) {
            $deployment = Invoke-AzureJson @('deployment', 'sub', 'show', '--name', 'graph-switchboard')
        } else {
            $foundationSucceeded = $false
            foreach ($databaseRegion in $DatabaseRegions) {
                $values = Get-Content -LiteralPath $foundationParameters -Raw | ConvertFrom-Json -AsHashtable
                $values.parameters.databaseLocation.value = $databaseRegion
                $values | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $foundationParameters -Encoding utf8
                Write-Output "Allocating PostgreSQL in $databaseRegion; hosting remains in $Location."
                try {
                    $deployment = Invoke-AzureJson @('deployment', 'sub', 'create', '--name', 'graph-switchboard',
                        '--location', $Location, '--template-file', '.\infra\subscription.bicep',
                        '--parameters', "@$foundationParameters")
                    $foundationSucceeded = $true
                    break
                } catch [InvalidOperationException] {
                    if (-not $_.Exception.Data['AzureDetails'] -or
                        -not $_.Exception.Data['AzureDetails'].Contains('RegionalAllocationFailed')) { throw }
                    $remaining = @(Invoke-AzureJson @('resource', 'list', '--resource-group', $ResourceGroup,
                        '--resource-type', 'Microsoft.DBforPostgreSQL/flexibleServers'))
                    if ($remaining.Count) {
                        throw "Capacity failure left a PostgreSQL resource in $databaseRegion; inspect it before retrying."
                    }
                    Write-Output "No B2s capacity in $databaseRegion; trying the next explicitly approved region."
                }
            }
            if (-not $foundationSucceeded) { throw 'All approved PostgreSQL regions rejected allocation.' }
        }
    } finally {
        Remove-Item -LiteralPath $foundationParameters -Force
        $adminPassword = $null
        $appPassword = $null
    }

    $infrastructure = $deployment.properties.outputs.infrastructure.value
    if (-not $infrastructure.registryName -or -not $infrastructure.origin) {
        throw 'Foundation deployment did not return required outputs.'
    }
    $infrastructure | ConvertTo-Json -Depth 10 | Set-Content '.azure\deployed.local.json'

    $registryId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.ContainerRegistry/registries/$($infrastructure.registryName)"
    $rolesReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $roles = Invoke-AzureJson @('role', 'assignment', 'list', '--scope', $registryId,
            '--fill-principal-name', 'false')
        $pullPrincipals = @($roles | Where-Object {
            $_.roleDefinitionId.EndsWith('/7f951dda-4ed3-4680-a7ca-43fe172d538d')
        } | ForEach-Object { $_.principalId })
        if ($infrastructure.runtimePrincipalId -in $pullPrincipals -and
            $infrastructure.bootstrapPrincipalId -in $pullPrincipals) {
            $rolesReady = $true
            break
        }
        Start-Sleep -Seconds 10
    }
    if (-not $rolesReady) { throw 'AcrPull assignments did not become visible for both identities.' }
    Write-Output 'Both managed identities have registry AcrPull access.'

    $preload = Invoke-AzureJson @('postgres', 'flexible-server', 'parameter', 'show',
        '--resource-group', $ResourceGroup, '--server-name', $infrastructure.databaseServerName,
        '--name', 'shared_preload_libraries')
    if ($preload.isConfigPendingRestart -eq $true -or $preload.isConfigPendingRestart -eq 'True') {
        Write-Output 'Restarting PostgreSQL to activate Apache AGE preload.'
        Invoke-Azure @('postgres', 'flexible-server', 'restart', '--resource-group', $ResourceGroup,
            '--name', $infrastructure.databaseServerName, '--output', 'none')
    }

    $usage = Invoke-AzureJson @('containerapp', 'env', 'list-usages',
        '--resource-group', $ResourceGroup, '--name', $infrastructure.environmentName)
    $usage | ConvertTo-Json -Depth 10 | Set-Content '.azure\environment-quotas.local.json'

    $sourceFiles = @(
        Get-Item '.\Dockerfile', '.\.dockerignore', '.\requirements.txt'
        Get-ChildItem '.\traversal' -Filter '*.py' -File
        Get-ChildItem '.\web' -File
        Get-ChildItem '.\data\traversal' -Recurse -File
        Get-ChildItem '.\.venv\wheelhouse' -Filter '*.whl' -File
    ) | Sort-Object FullName
    $hashes = ($sourceFiles | Get-FileHash -Algorithm SHA256).Hash -join ''
    $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($hashes))).ToLower()
    $image = "$($infrastructure.registryServer)/graph-switchboard:$($digest.Substring(0, 16))"
    Write-Output "Building application image $image"
    & docker build --quiet --tag $image .
    if ($LASTEXITCODE -ne 0) { throw 'Container image build failed.' }
    $login = Invoke-AzureJson @('acr', 'login', '--name', $infrastructure.registryName, '--expose-token')
    $login.accessToken | & docker login $infrastructure.registryServer --username '00000000-0000-0000-0000-000000000000' --password-stdin
    if ($LASTEXITCODE -ne 0) { throw 'Container registry login failed.' }
    $login = $null
    & docker push --quiet $image
    if ($LASTEXITCODE -ne 0) { throw 'Container image push failed.' }
    $manifest = Invoke-AzureJson @('acr', 'repository', 'show', '--name', $infrastructure.registryName,
        '--image', "graph-switchboard:$($digest.Substring(0, 16))")
    if ($manifest.digest -notmatch '^sha256:[a-f0-9]{64}$') {
        throw 'The published registry manifest did not return an immutable digest.'
    }
    $image = "$($infrastructure.registryServer)/graph-switchboard@$($manifest.digest)"

    $accessParameters = Write-Parameters 'foundry-access' @{
        accountName = $FoundryAccount
        runtimePrincipalId = $infrastructure.runtimePrincipalId
    }
    try {
        Invoke-Azure @('deployment', 'group', 'create', '--resource-group', $FoundryResourceGroup,
            '--name', 'graph-switchboard-inference', '--template-file', '.\infra\foundry-access.bicep',
            '--parameters', "@$accessParameters", '--output', 'none')
    } finally { Remove-Item -LiteralPath $accessParameters -Force }

    $config = if (Test-Path -LiteralPath $ConfigPath) {
        Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json -AsHashtable
    } else {
        @{
            endpoint = "https://$FoundryAccount.cognitiveservices.azure.com"
            decision_deployment = 'Decision-1'
            baseline_deployment = 'gpt-6-sol'
            pricing = @{
                source = '2026-10-19: https://commandline.microsoft.com/microsoft-decision-1-model-foundry/; https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-6-sol'
                decision = @{ input = 0.042; output = 0 }
                baseline = @{ input = 2.0; output = 10.0; cached_input = 0.20 }
            }
        }
    }
    $applicationValues = @{
        appName = $infrastructure.appName
        environmentName = $infrastructure.environmentName
        runtimeIdentityName = $infrastructure.runtimeIdentityName
        bootstrapIdentityName = $infrastructure.bootstrapIdentityName
        registryName = $infrastructure.registryName
        vaultName = $infrastructure.vaultName
        image = $image
        foundryEndpoint = $config.endpoint
        decisionDeployment = $config.decision_deployment
        llmDeployment = $config.baseline_deployment
        pricingJson = ConvertTo-Json -InputObject $config.pricing -Compress -Depth 10
        enableApp = $false
    }
    $appParameters = Write-Parameters 'application' $applicationValues
    try {
        $bootstrapDeployment = Invoke-AzureJson @('deployment', 'group', 'create', '--resource-group', $ResourceGroup,
            '--name', 'graph-switchboard-bootstrap', '--template-file', '.\infra\application.bicep',
            '--parameters', "@$appParameters")
        $bootstrapJobName = $bootstrapDeployment.properties.outputs.bootstrapJobName.value
        if (-not $bootstrapJobName) { throw 'Bootstrap deployment did not return its job name.' }
        $execution = Invoke-AzureJson @('containerapp', 'job', 'start', '--resource-group', $ResourceGroup,
            '--name', $bootstrapJobName)
        $executionName = $execution.name
        if (-not $executionName) { throw 'Bootstrap did not return an execution name.' }
        $jobSucceeded = $false
        for ($attempt = 0; $attempt -lt 180; $attempt++) {
            $state = Invoke-AzureJson @('containerapp', 'job', 'execution', 'show',
                '--resource-group', $ResourceGroup, '--name', $bootstrapJobName,
                '--job-execution-name', $executionName)
            if ($state.properties.status -eq 'Succeeded') { $jobSucceeded = $true; break }
            if ($state.properties.status -in @('Failed', 'Degraded', 'Stopped')) {
                throw "Database bootstrap failed: $executionName; inspect job logs."
            }
            Start-Sleep -Seconds 5
        }
        if (-not $jobSucceeded) { throw 'Database bootstrap did not complete within 15 minutes.' }
        Write-Output 'Private AGE graph, application role and durable run store initialized.'

        $applicationValues.enableApp = $true
        $appParameters = Write-Parameters 'application' $applicationValues
        Invoke-Azure @('deployment', 'group', 'create', '--resource-group', $ResourceGroup,
            '--name', 'graph-switchboard-application', '--template-file', '.\infra\application.bicep',
            '--parameters', "@$appParameters", '--output', 'none')
    } finally { Remove-Item -LiteralPath $appParameters -Force }

    Wait-Healthy $infrastructure.origin
    $catalog = Invoke-RestMethod "$($infrastructure.origin)/api/catalog" -TimeoutSec 30
    if (-not $catalog.cases) { throw 'Deployed catalog did not contain comparison cases.' }
    @{
        origin = $infrastructure.origin
        image = $image
        deployed_at = [DateTime]::UtcNow.ToString('o')
        bootstrap_execution = $executionName
        resource_group = $ResourceGroup
    } | ConvertTo-Json | Set-Content '.azure\release.local.json'
    Write-Output "Live demo ready: $($infrastructure.origin)"
} finally {
    Pop-Location
}
