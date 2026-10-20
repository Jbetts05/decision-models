targetScope = 'subscription'

param location string = 'swedencentral'
param databaseLocation string = 'northeurope'
param resourceGroupName string = 'rg-graph-switchboard'
@secure()
param administratorPassword string
@secure()
param applicationPassword string

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    application: 'graph-switchboard'
    purpose: 'live-demo'
  }
}

module foundation './main.bicep' = {
  name: 'graph-switchboard-foundation'
  scope: group
  params: {
    location: location
    databaseLocation: databaseLocation
    administratorPassword: administratorPassword
    applicationPassword: applicationPassword
  }
}

output infrastructure object = {
  resourceGroupName: group.name
  registryName: foundation.outputs.registryName
  registryServer: foundation.outputs.registryServer
  environmentName: foundation.outputs.environmentName
  runtimeIdentityName: foundation.outputs.runtimeIdentityName
  runtimePrincipalId: foundation.outputs.runtimePrincipalId
  bootstrapIdentityName: foundation.outputs.bootstrapIdentityName
  bootstrapPrincipalId: foundation.outputs.bootstrapPrincipalId
  vaultName: foundation.outputs.vaultName
  databaseServerName: foundation.outputs.databaseServerName
  databaseLocation: foundation.outputs.databaseLocation
  appName: foundation.outputs.appName
  origin: foundation.outputs.origin
}
