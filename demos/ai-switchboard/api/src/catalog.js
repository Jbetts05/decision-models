const modelDefinitions = Object.freeze([
  Object.freeze({ id: 'decision', name: 'Microsoft Decision One', deployment: 'Decision-1', setting: 'DECISION_DEPLOYMENT' }),
  Object.freeze({ id: 'astra', name: 'GPT-6 Astra', deployment: 'gpt-6-astra', setting: 'ASTRA_DEPLOYMENT' }),
  Object.freeze({ id: 'sol', name: 'GPT-6 Sol', deployment: 'gpt-6-sol', setting: 'SOL_DEPLOYMENT' }),
  Object.freeze({ id: 'luna', name: 'GPT-6 Luna', deployment: 'gpt-6-luna', setting: 'LUNA_DEPLOYMENT' }),
]);

const ticketCriteria = Object.freeze({
  Billing: 'Payments, charges, refunds, invoices, or other billing problems.',
  Account: 'Sign-in, account access, passwords, or identity verification.',
  Technical: 'Product failures, integrations, API errors, or broken functionality.',
});
const complaintCriteria = Object.freeze({
  Delivery: 'A complaint primarily about delivery timing or the arrival of an order.',
  Subscription: 'A complaint primarily about subscription terms, renewal, or cancellation.',
  'Multiple issues': 'A complaint involving two or more substantial, distinct categories of concern.',
});
const agentCriteria = Object.freeze({
  'Research agent': 'Investigate sources, compare evidence, and produce a sourced research summary.',
  'Coding agent': 'Implement, debug, or test software and work with code.',
  'General assistant': 'Writing, planning, or general help that does not require research or software changes.',
});
const ticketInstructions = 'Route this fictional support ticket to exactly one team using the category definitions. Choose the team best suited to the main issue.';
const complaintInstructions = 'Classify this fictional customer complaint into exactly one category using the definitions. Use Multiple issues when distinct substantial concerns are present.';
const agentInstructions = 'Select exactly one agent for this fictional task using the capability definitions. Choose the agent best suited to the main work requested.';

const scenarios = Object.freeze([
  {
    id: 'ticket-duplicate-charge',
    title: 'Ticket routing · Duplicate charge',
    question: 'Which team should handle this ticket?',
    instructions: ticketInstructions,
    criteria: ticketCriteria,
    text: 'The Moonbeam Museum charged me twice for one midnight dinosaur tour. Both payments cleared, but I received only one ticket. Please refund the duplicate charge.',
  },
  {
    id: 'ticket-locked-account',
    title: 'Ticket routing · Locked account',
    question: 'Which team should handle this ticket?',
    instructions: ticketInstructions,
    criteria: ticketCriteria,
    text: 'I am locked out of my Cloud Castle account after changing phones. The old device receives the verification code, and resetting my password has not restored access.',
  },
  {
    id: 'ticket-integration-error',
    title: 'Ticket routing · Integration error',
    question: 'Which team should handle this ticket?',
    instructions: ticketInstructions,
    criteria: ticketCriteria,
    text: 'Our Starling Robotics inventory integration now returns HTTP 500 when syncing clockwork owls. Sign-in works and invoices look correct. The same request worked yesterday.',
  },
  {
    id: 'complaint-late-delivery',
    title: 'Complaint category · Late delivery',
    question: 'What kind of complaint is this?',
    instructions: complaintInstructions,
    criteria: complaintCriteria,
    text: 'The glow-in-the-dark garden gnome I ordered for Saturday arrived on Wednesday. The product is lovely, but missing the promised delivery date spoiled the party.',
  },
  {
    id: 'complaint-misleading-subscription',
    title: 'Complaint category · Misleading subscription',
    question: 'What kind of complaint is this?',
    instructions: complaintInstructions,
    criteria: complaintCriteria,
    text: 'Your Dragon Gazette trial said cancel anytime, but the cancellation page says I must pay for a full year. That restriction was not clear when I subscribed.',
  },
  {
    id: 'complaint-multi-issue',
    title: 'Complaint category · Multi-issue',
    question: 'What kind of complaint is this?',
    instructions: complaintInstructions,
    criteria: complaintCriteria,
    text: 'My monthly miniature-moon box arrived ten days late with a cracked moon inside. I also tried to cancel, but your site renewed the subscription after confirming cancellation.',
  },
  {
    id: 'agent-research-task',
    title: 'Agent selection · Research task',
    question: 'Which agent should take this task?',
    instructions: agentInstructions,
    criteria: agentCriteria,
    text: 'Investigate whether our fictional floating library should use wind or solar power. Compare credible sources, explain the uncertainties, and write a brief with citations.',
  },
  {
    id: 'agent-coding-task',
    title: 'Agent selection · Coding task',
    question: 'Which agent should take this task?',
    instructions: agentInstructions,
    criteria: agentCriteria,
    text: 'Fix the JavaScript reservation service for our imaginary underwater cinema. Find why duplicate bookings slip through, implement a fix, and add regression tests.',
  },
].map(Object.freeze));

function getModels(env = process.env) {
  return modelDefinitions.map(({ id, name, deployment, setting }) => ({
    id,
    name,
    deployment: env[setting]?.trim() || deployment,
  }));
}

function getCatalog(env = process.env) {
  return { models: getModels(env), scenarios: structuredClone(scenarios) };
}

module.exports = { getCatalog, getModels, scenarios };
