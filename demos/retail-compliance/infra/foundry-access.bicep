@description('Existing Foundry (AI Services) account name.')
param accountName string

@description('Principal ID of the demo managed identity.')
param principalId string

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: accountName
}

// Inference only: read the account and call decision models
// (/providers/microsoft/v1/systemone). Cannot list keys or manage agents, files,
// assistants or deployments.
resource inferenceRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'shelf-check-inference-only')
  properties: {
    roleName: 'Shelf Check inference only (${resourceGroup().name})'
    description: 'Call Foundry decision-model inference on accounts in this resource group, without listing keys.'
    type: 'CustomRole'
    assignableScopes: [ resourceGroup().id ]
    permissions: [ {
      actions: [ 'Microsoft.CognitiveServices/accounts/read' ]
      dataActions: [ 'Microsoft.CognitiveServices/accounts/AIServices/providers/action' ]
    } ]
  }
}

resource access 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, inferenceRole.id)
  scope: account
  properties: { roleDefinitionId: inferenceRole.id, principalId: principalId, principalType: 'ServicePrincipal' }
}
