targetScope = 'resourceGroup'

@description('Azure region for the demo resources.')
param location string = resourceGroup().location

@description('Short lowercase prefix for resource names.')
@minLength(3)
@maxLength(12)
param namePrefix string = 'shelfcheck'

@description('Name of the existing Foundry (AI Services) account that hosts the Decision-1.1 deployment.')
param foundryAccountName string

@description('Resource group of the existing Foundry account.')
param foundryResourceGroup string

@description('HTTPS endpoint of the Foundry account, without a path.')
param foundryEndpoint string

@description('Decision-1.1 deployment name on the Foundry account.')
param decisionDeployment string

@description('Server-side limit on Decision-1.1 calls per UTC day.')
@minValue(1)
param dailyMaxCalls int = 2000

@description('Container image to run. Leave empty on the first pass, before the image is built.')
param image string = ''

var suffix = uniqueString(resourceGroup().id)
var acrPullRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs-${suffix}'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${namePrefix}${suffix}'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-${suffix}'
  location: location
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRole)
  scope: registry
  properties: { roleDefinitionId: acrPullRole, principalId: identity.properties.principalId, principalType: 'ServicePrincipal' }
}

module foundryAccess 'foundry-access.bicep' = {
  name: 'foundry-access-${suffix}'
  scope: resourceGroup(foundryResourceGroup)
  params: { accountName: foundryAccountName, principalId: identity.properties.principalId }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = if (!empty(image)) {
  name: '${namePrefix}-app'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    environmentId: environment.id
    configuration: {
      ingress: { external: true, targetPort: 8080, transport: 'auto', allowInsecure: false }
      registries: [ { server: registry.properties.loginServer, identity: identity.id } ]
    }
    template: {
      containers: [ {
        name: 'web'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'FOUNDRY_ENDPOINT', value: foundryEndpoint }
          { name: 'DECISION_DEPLOYMENT', value: decisionDeployment }
          { name: 'FOUNDRY_AUTH_MODE', value: 'managed_identity' }
          { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          { name: 'DAILY_MAX_CALLS', value: string(dailyMaxCalls) }
        ]
        probes: [ { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 30 } ]
      } ]
      // One replica keeps the in-memory daily call limit shared.
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
  dependsOn: [ pull, foundryAccess ]
}

output registryName string = registry.name
output appUrl string = empty(image) ? '' : 'https://${app!.properties.configuration.ingress.fqdn}'
