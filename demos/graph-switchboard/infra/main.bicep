targetScope = 'resourceGroup'

param location string = resourceGroup().location
param databaseLocation string = 'northeurope'
@secure()
param administratorPassword string
@secure()
param applicationPassword string

var suffix = uniqueString(subscription().id, resourceGroup().id)
var appName = 'graph-switchboard-${suffix}'
var tags = {
  application: 'graph-switchboard'
  purpose: 'live-demo'
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-graph-runtime-${suffix}'
  location: location
  tags: tags
}

resource bootstrapIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-graph-bootstrap-${suffix}'
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crgraph${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource registryRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in range(0, 2): {
  name: guid(registry.id, [runtimeIdentity.id, bootstrapIdentity.id][i], 'AcrPull')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: [runtimeIdentity.properties.principalId, bootstrapIdentity.properties.principalId][i]
    principalType: 'ServicePrincipal'
  }
}]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-graph-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource databaseNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-graph-postgres-${suffix}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAppPostgres'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.42.0.0/23'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.42.3.0/27'
          destinationPortRange: '5432'
        }
      }
      {
        name: 'AllowAppKeyVault'
        properties: {
          priority: 105
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.42.0.0/23'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.42.3.0/27'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowDatabaseInternal'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: '10.42.2.0/27'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.42.2.0/27'
          destinationPortRange: '*'
        }
      }
      {
        name: 'DenyOtherVnetInbound'
        properties: {
          priority: 200
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-graph-${suffix}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'apps'
        properties: {
          addressPrefix: '10.42.0.0/23'
          delegations: [
            {
              name: 'container-apps'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: '10.42.2.0/27'
          networkSecurityGroup: {
            id: databaseNsg.id
          }
          delegations: [
            {
              name: 'postgres'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.42.3.0/27'
          privateEndpointNetworkPolicies: 'Enabled'
          networkSecurityGroup: {
            id: databaseNsg.id
          }
        }
      }
    ]
  }
}

resource dns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dns
  name: 'graph-network'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: network.id
    }
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'env-graph-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: '${network.id}/subnets/apps'
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'pg-graph-${databaseLocation}-${suffix}'
  location: databaseLocation
  tags: tags
  sku: {
    name: 'Standard_B2s'
    tier: 'Burstable'
  }
  properties: {
    version: '17'
    administratorLogin: 'graph_admin'
    administratorLoginPassword: administratorPassword
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Disabled'
    }
  }
  dependsOn: [
    dnsLink
  ]
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-graph-postgres-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${network.id}/subnets/private-endpoints'
    }
    privateLinkServiceConnections: [
      {
        name: 'graph-postgres'
        properties: {
          privateLinkServiceId: postgres.id
          groupIds: [
            'postgresqlServer'
          ]
        }
      }
    ]
  }
}

resource endpointDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'postgres'
        properties: {
          privateDnsZoneId: dns.id
        }
      }
    ]
  }
}

resource extensionAllowlist 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'AGE'
    source: 'user-override'
  }
}

resource preload 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'shared_preload_libraries'
  properties: {
    value: 'age,pg_stat_statements'
    source: 'user-override'
  }
  dependsOn: [
    extensionAllowlist
  ]
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'traversal'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-graph-${suffix}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    publicNetworkAccess: 'Disabled'
    enableSoftDelete: true
    enablePurgeProtection: true
    softDeleteRetentionInDays: 7
    accessPolicies: []
  }
}

resource vaultDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource vaultDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: vaultDns
  name: 'graph-network'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: network.id
    }
  }
}

resource vaultEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-graph-vault-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${network.id}/subnets/private-endpoints'
    }
    privateLinkServiceConnections: [
      {
        name: 'graph-vault'
        properties: {
          privateLinkServiceId: vault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource vaultEndpointDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: vaultEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'vault'
        properties: {
          privateDnsZoneId: vaultDns.id
        }
      }
    ]
  }
  dependsOn: [
    vaultDnsLink
  ]
}

var tls = 'sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
resource runtimeSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'runtime-database-url'
  properties: {
    value: 'postgresql://traversal_app:${uriComponent(applicationPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/traversal?${tls}'
  }
}

resource adminSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'bootstrap-database-url'
  properties: {
    value: 'postgresql://graph_admin:${uriComponent(administratorPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/traversal?${tls}'
  }
}

resource passwordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'application-database-password'
  properties: {
    value: applicationPassword
  }
}

resource runtimeSecretRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(runtimeSecret.id, runtimeIdentity.id, 'SecretsUser')
  scope: runtimeSecret
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource bootstrapSecretRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, bootstrapIdentity.id, 'SecretsUser')
  scope: vault
  properties: {
    principalId: bootstrapIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

output registryName string = registry.name
output registryServer string = registry.properties.loginServer
output environmentName string = environment.name
output runtimeIdentityName string = runtimeIdentity.name
output runtimePrincipalId string = runtimeIdentity.properties.principalId
output bootstrapIdentityName string = bootstrapIdentity.name
output bootstrapPrincipalId string = bootstrapIdentity.properties.principalId
output vaultName string = vault.name
output databaseServerName string = postgres.name
output databaseLocation string = databaseLocation
output appName string = appName
output origin string = 'https://${appName}.${environment.properties.defaultDomain}'
