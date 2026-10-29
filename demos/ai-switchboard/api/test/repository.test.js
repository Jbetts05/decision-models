const test = require('node:test');
const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const { dirname, join, resolve } = require('node:path');

const demo = resolve(__dirname, '..', '..');
const root = resolve(demo, '..', '..');

test('AI Switchboard is the first demo in the source-first central catalogue', () => {
  const readme = readFileSync(join(root, 'README.md'), 'utf8');
  assert.match(readme, /## Start here: AI Switchboard/);
  assert.match(readme, /\[Source and setup\]\(demos\/ai-switchboard\/README\.md\)/);
  const headings = readme.split(/\r?\n/).filter(line => line.startsWith('## '));
  assert.deepEqual(headings.slice(0, 4), [
    '## Start here: AI Switchboard',
    '## Next: Graph Switchboard',
    '## Get the source',
    '## Repository layout',
  ]);
  assert.ok(!headings.includes('## Demos'));
});

test('public guides do not link to maintainer-hosted demo instances', () => {
  for (const path of [
    join(root, 'README.md'), join(demo, 'README.md'),
    join(demo, 'docs', 'deployment.md'),
    join(root, 'demos', 'graph-switchboard', 'README.md'),
    join(root, 'demos', 'graph-switchboard', 'docs', 'graph-switchboard-history.md'),
  ]) {
    const readme = readFileSync(path, 'utf8');
    assert.doesNotMatch(readme, /https:\/\/[^\s)]+(?:azurestaticapps\.net|azurecontainerapps\.io)/);
    assert.doesNotMatch(readme, /Open the live/);
  }
});

test('central and AI Switchboard guides have resolvable local links', () => {
  for (const path of [
    join(root, 'README.md'), join(demo, 'README.md'),
    join(demo, 'api', 'README.md'), join(demo, 'docs', 'deployment.md'),
  ]) {
    const readme = readFileSync(path, 'utf8');
    for (const [, target] of readme.matchAll(/\]\(([^)\s]+)\)/g)) {
      if (target.includes('://') || target.startsWith('#')) continue;
      assert.ok(existsSync(resolve(dirname(path), target.split('#')[0])), `${path}: ${target}`);
    }
  }
});

test('central deployment is manual, isolated and uses the demo subdirectory', () => {
  const workflow = readFileSync(join(root, '.github', 'workflows', 'ai-switchboard.yml'), 'utf8');
  const deployment = workflow.slice(workflow.indexOf('\n  deploy:'));
  assert.match(deployment, /if: github\.event_name == 'workflow_dispatch' && inputs\.deploy/);
  assert.match(deployment, /secrets\.AI_SWITCHBOARD_DEPLOYMENT_TOKEN/);
  assert.match(deployment, /app_location: demos\/ai-switchboard\/web/);
  assert.match(deployment, /api_location: demos\/ai-switchboard\/api/);
  assert.ok(!workflow.includes('secrets.AZURE_STATIC_WEB_APPS_API_TOKEN'));
});

test('the central copy records its origin without importing maintainer provisioning state', () => {
  const readme = readFileSync(join(demo, 'README.md'), 'utf8');
  assert.ok(readme.includes('b153122d5892428fcbdfd9b42e0658c14ae43615'));
  assert.ok(!existsSync(join(demo, '.git')));
  assert.ok(!existsSync(join(demo, 'scripts', 'provision.ps1')));
  assert.ok(!existsSync(join(demo, 'infra', 'main.parameters.json')));
});
