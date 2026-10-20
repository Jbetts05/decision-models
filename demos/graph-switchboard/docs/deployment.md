# Deploy your own Azure instance

Local setup is the shortest route to trying the demo. Azure deployment is
optional and creates chargeable resources and scoped role assignments.
Use your own subscription and existing Foundry deployments; the scripts contain
no default owner subscription, Foundry account or resource endpoint.

## Architecture and prerequisites

- PowerShell **7.2+**, Azure CLI with Bicep, Docker, and this demo's configured
  `.venv` and `config.local.json`.
- An existing Foundry resource with Decision-1 and Sol deployments, plus
  permission to deploy resources and assign the required scoped roles.
- Capacity and policy approval for Container Apps, ACR, Key Vault and PostgreSQL.

The templates provision HTTPS Container Apps, a private PostgreSQL Flexible
Server with AGE, ACR, Key Vault, private endpoints/DNS and separate runtime and
bootstrap managed identities. PostgreSQL and Key Vault are not exposed through
public database firewall rules. A one-shot private-network bootstrap loads the
graph and verifies the narrower runtime database permissions.

The default host region is Sweden Central. The script tries the explicitly
supplied PostgreSQL region list on capacity failures, in order. Approve those
regions and their cross-region networking/data-location implications first.

## Configure, validate, deploy

Run from `demos\graph-switchboard`. Complete the local setup first, then use
**your own identifiers**:

```powershell
$deployment = @{
    SubscriptionId      = "YOUR-SUBSCRIPTION-ID"
    FoundryResourceGroup = "YOUR-FOUNDRY-RESOURCE-GROUP"
    FoundryAccount      = "YOUR-FOUNDRY-ACCOUNT"
    ResourceGroup       = "rg-graph-switchboard"
    Location            = "swedencentral"
    DatabaseRegions     = @("northeurope")
}

.\infra\deploy.ps1 @deployment -ValidateOnly
```

Review validation, what-if, regional capacity and costs. **ValidateOnly is not a
pure offline check:** it uses Azure validation/what-if, downloads Linux wheels
and may create ignored local encrypted credential state. It does not deploy the
application. After approval, execute:

```powershell
.\infra\deploy.ps1 @deployment
```

The script builds a content-addressed image, provisions the infrastructure,
assigns scoped inference access, bootstraps the private database, deploys the
app and checks readiness. Its final output includes the live URL. Deployment
outputs are saved under ignored `.azure/`.

On Windows, deployment passwords are retained using current-user DPAPI in
`.azure/deployment-secrets.clixml`. Preserve this local file for repeat
deployments; never commit or share it. Outside Windows, supply stable
`GRAPH_ADMIN_PASSWORD` and `GRAPH_APP_PASSWORD` environment secrets instead.
Do not generate new passwords for an existing deployment.

The script downloads Linux dependency wheels through the host into
`.venv/wheelhouse/`. The Dockerfile installs them offline into an image-local
virtual environment. A bare `docker build` before preparing these wheels is not
the documented build path.

## After deployment

- `/health/live` checks the process. `/health/ready` checks real database and
  graph availability without invoking a model.
- Anyone who can reach the unauthenticated application may trigger paid model
  calls. Confirm your intended audience and server-side call limit before
  sharing the URL. An unlisted URL is not access control.
- `SERVER_DAILY_MAX_CALLS` defaults to 1,000 attempted calls per UTC day, with
  durable admission and one globally active comparison.
- Run records and graph data persist across application revisions. Deleting
  Azure resources is not part of the startup or shutdown instructions.

For an existing deployment, retain its original subscription, resource group,
Foundry settings and local encrypted state. Moving the repository files does
not change or redeploy any Azure resource.
