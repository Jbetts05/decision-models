targetScope = 'resourceGroup'

param accountName string
param runtimePrincipalId string

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: accountName
}

resource inferenceAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, runtimePrincipalId, 'graph-inference')
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
  }
}
