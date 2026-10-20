targetScope = 'resourceGroup'

param location string = resourceGroup().location
param appName string
param environmentName string
param runtimeIdentityName string
param bootstrapIdentityName string
param registryName string
param vaultName string
param image string
param enableApp bool = false
param foundryEndpoint string
param decisionDeployment string = 'Decision-1'
param llmDeployment string = 'gpt-6-sol'
param dailyMaxCalls int = 1000
param pricingJson string = '{}'

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}
resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: runtimeIdentityName
}
resource bootstrapIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: bootstrapIdentityName
}
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
}

resource bootstrap 'Microsoft.App/jobs@2024-03-01' = {
  name: 'graph-seed-${uniqueString(subscription().id, resourceGroup().id)}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${bootstrapIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 900
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: bootstrapIdentity.id
        }
      ]
      secrets: [
        {
          name: 'admin-database'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/bootstrap-database-url'
          identity: bootstrapIdentity.id
        }
        {
          name: 'app-password'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/application-database-password'
          identity: bootstrapIdentity.id
        }
        {
          name: 'app-database'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/runtime-database-url'
          identity: bootstrapIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'bootstrap'
          image: image
          command: [
            'python'
            '-m'
            'traversal'
          ]
          args: [
            'bootstrap'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'admin-database' }
            { name: 'APP_DATABASE_PASSWORD', secretRef: 'app-password' }
            { name: 'APP_DATABASE_URL', secretRef: 'app-database' }
            { name: 'AGE_PRELOADED', value: '1' }
          ]
        }
      ]
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = if (enableApp) {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'http'
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: runtimeIdentity.id
        }
      ]
      secrets: [
        {
          name: 'app-database'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/runtime-database-url'
          identity: runtimeIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'graph-switchboard'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'app-database' }
            { name: 'AGE_PRELOADED', value: '1' }
            { name: 'APP_STORE_INITIALIZE', value: '0' }
            { name: 'FOUNDRY_ENDPOINT', value: foundryEndpoint }
            { name: 'DECISION_DEPLOYMENT', value: decisionDeployment }
            { name: 'LLM_DEPLOYMENT', value: llmDeployment }
            { name: 'FOUNDRY_AUTH_MODE', value: 'managed_identity' }
            { name: 'AZURE_CLIENT_ID', value: runtimeIdentity.properties.clientId }
            { name: 'PUBLIC_ORIGIN', value: 'https://${appName}.${environment.properties.defaultDomain}' }
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'PORT', value: '8080' }
            { name: 'SERVER_DAILY_MAX_CALLS', value: string(dailyMaxCalls) }
            { name: 'FOUNDRY_PRICING_JSON', value: pricingJson }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health/live', port: 8080 }
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 60
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health/live', port: 8080 }
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/ready', port: 8080 }
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output origin string = 'https://${appName}.${environment.properties.defaultDomain}'
output bootstrapJobName string = bootstrap.name
