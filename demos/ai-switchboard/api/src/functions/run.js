const { app } = require('@azure/functions');
const { createRunHandler } = require('../core');

app.http('run', {
  methods: ['POST'],
  authLevel: 'anonymous',
  route: 'run',
  handler: createRunHandler(),
});
