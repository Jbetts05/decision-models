# Deploy your own AI Switchboard

Deploy a separate instance with your own models and billing using this guide.
The original repository and deployment are not modified by the central import.

## 1. Prepare Azure

You need an Azure Static Web App with a managed **Node.js 22 Functions API**,
and a Foundry resource with these deployments:

| Model | Default deployment name |
| --- | --- |
| Microsoft Decision One | `Decision-1` |
| GPT-6 Astra | `gpt-6-astra` |
| GPT-6 Sol | `gpt-6-sol` |
| GPT-6 Luna | `gpt-6-luna` |

Use a **separate Static Web App** for this copy. You can create one with deployment
source **Other**, or use [`infra/main.bicep`](../infra/main.bicep) in your own
resource group. The template creates only the Static Web App, not Foundry or model
deployments. Review region, policies and costs before creating resources.

## 2. Configure the API

In that Static Web App's encrypted application settings, set:

| Setting | Value |
| --- | --- |
| `FOUNDRY_ENDPOINT` | Your HTTPS Foundry resource origin, such as `https://YOUR-RESOURCE.services.ai.azure.com` |
| `FOUNDRY_API_KEY` | A key for that resource |

Use the resource origin without a project/inference path. Both settings are
required in this copy. Never add the key to Git, the frontend, a URL or a README.

If your deployment names differ, also set `DECISION_DEPLOYMENT`,
`ASTRA_DEPLOYMENT`, `SOL_DEPLOYMENT` and `LUNA_DEPLOYMENT`.

## 3. Deploy manually

In the central repository's GitHub Actions secrets, set
**`AI_SWITCHBOARD_DEPLOYMENT_TOKEN`** to the deployment token for **your chosen
Static Web App**. Verify the target before using it. Do not copy the original
demo's token unless you deliberately intend to deploy to that existing site.

In **Actions > AI Switchboard > Run workflow**, choose the intended branch and
enable **Deploy to your configured Static Web App**.

The [workflow](../../../.github/workflows/ai-switchboard.yml) runs offline tests
first, then uploads `demos/ai-switchboard/web` and `demos/ai-switchboard/api`.
Its build installs the API's Functions dependency in an isolated build environment.
Normal pushes and pull requests run tests only; **they do not deploy**.

Open the URL for your Static Web App. `/api/catalog` should return four models
and eight scenarios without invoking inference. Selecting **Run comparison**
then makes four live model requests.

## Operating limits

The app is anonymous and uses the owner's Foundry quota. Its limiter is
process-local: 16 concurrent requests and 96 starts per rolling minute per API
instance. Restarts reset it and scaled instances have independent counters.
This is not a global request limit or spending cap.

Use fictional inputs only. The application does not persist submissions, but
the text is sent to the configured Foundry models. No database, Docker, Python
environment or Graph Switchboard configuration is needed.
