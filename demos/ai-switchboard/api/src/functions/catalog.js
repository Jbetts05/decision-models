const { app } = require('@azure/functions');
const { handleCatalog } = require('../core');

app.http('catalog', {
  methods: ['GET'],
  authLevel: 'anonymous',
  route: 'catalog',
  handler: handleCatalog,
});
