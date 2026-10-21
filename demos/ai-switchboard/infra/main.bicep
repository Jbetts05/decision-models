targetScope = 'resourceGroup'

param name string = 'ai-switchboard'
param location string = 'westeurope'

resource site 'Microsoft.Web/staticSites@2024-11-01' = {
  name: name
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    buildProperties: {
      appLocation: 'demos/ai-switchboard/web'
      apiLocation: 'demos/ai-switchboard/api'
      appArtifactLocation: ''
    }
  }
}

output hostname string = site.properties.defaultHostname
