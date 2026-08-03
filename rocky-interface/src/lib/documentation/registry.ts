export type DocumentationCategory = 'developer' | 'examples' | 'administration';

export type DocumentationDocument = {
	id: string;
	title: string;
	description: string;
	category: DocumentationCategory;
	audience: 'all' | 'administration';
	order: number;
	path: string;
};

export const documentation: DocumentationDocument[] = [
	{ id: 'intro', title: 'Getting Started', description: 'Learn the fundamentals of APIs, requests, responses, and authentication.', category: 'developer', audience: 'all', order: 1, path: '/docs/developer/getting-started.md' },
	{ id: 'apikey', title: 'API Keys', description: 'Generate and manage your Rocky API key.', category: 'developer', audience: 'all', order: 2, path: '/docs/developer/api-keys.md' },
	{ id: 'best-practices', title: 'Best Practices', description: 'Keep your API keys secure and use the API responsibly.', category: 'developer', audience: 'all', order: 3, path: '/docs/developer/best-practices.md' },
	{ id: 'reference', title: 'API Reference', description: 'Browse endpoints, parameters, and response formats.', category: 'developer', audience: 'all', order: 4, path: '/docs/developer/api-reference.md' },
	{ id: 'python', title: 'Python Example', description: 'Make your first Rocky API request using Python.', category: 'examples', audience: 'all', order: 1, path: '/docs/developer/python-example.md' },
	{ id: 'javascript', title: 'JavaScript Example', description: 'Connect to the Rocky API using JavaScript.', category: 'examples', audience: 'all', order: 2, path: '/docs/developer/javascript-example.md' },
	{ id: 'curl', title: 'curl Example', description: 'Send a copyable Rocky API request from a terminal.', category: 'examples', audience: 'all', order: 3, path: '/docs/developer/curl-example.md' },
	{ id: 'course-roster', title: 'Course Roster Workflow', description: 'Learn how to edit a course roster, add students manually, import a Canvas CSV, and confirm enrollment.', category: 'administration', audience: 'administration', order: 1, path: '/docs/administration/course-roster-workflow.md' },
	{ id: 'user-management', title: 'User Management', description: 'Manage users, search accounts, update roles, activate or deactivate accounts, and perform bulk user management.', category: 'administration', audience: 'administration', order: 2, path: '/docs/administration/user-management.md' },
	{ id: 'api-key-management', title: 'Managing API Keys', description: 'View, search, filter, activate, deactivate, and manage API keys for users and courses.', category: 'administration', audience: 'administration', order: 3, path: '/docs/administration/managing-api-keys.md' },
	{ id: 'admin-dashboard', title: 'Admin Dashboard', description: 'Learn how to use the dashboard, analytics, audit logs, system metrics, and other administrative tools.', category: 'administration', audience: 'administration', order: 4, path: '/docs/administration/admin-dashboard.md' }
];

export const documentsForCategory = (category: DocumentationCategory) =>
	documentation.filter((document) => document.category === category).sort((a, b) => a.order - b.order);
