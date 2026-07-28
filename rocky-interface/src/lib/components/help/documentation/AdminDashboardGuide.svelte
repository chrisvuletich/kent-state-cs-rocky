<script lang="ts">
	import { IconInfoCircle } from '@tabler/icons-svelte';
</script>

<div class="api-doc">
	<h1>Admin Dashboard</h1>
	<div class="api-callout"><div class="api-callout-icon"><IconInfoCircle size={30} stroke={2} /></div><div class="api-callout-content"><h3>For instructors and administrators</h3><p>Use this guide for a quick Rocky activity overview. Estimated reading time: 2–3 minutes.</p></div></div>
	<p class="api-doc-lead">The Admin Dashboard summarizes current Rocky data and provides quick access to administrative information.</p>

	<section class="api-doc-section"><h2>1. Read the dashboard overview</h2><p><strong>Total Users</strong> counts loaded user accounts, <strong>Active Users</strong> counts active accounts, and <strong>Total Courses</strong> counts loaded courses. <strong>API Keys Issued</strong> counts API-key summaries returned for those courses. <strong>Requests Today</strong> counts recorded request events dated today when the dashboard loads.</p><img class="documentation-screenshot" src="/Admin-1.Panel.png" alt="Admin Dashboard showing summary cards, audit logs, system status, and top active courses" /><p class="documentation-screenshot-caption">The dashboard provides an overview of administrative information and activity.</p></section>
	<section class="api-doc-section"><h2>2. Review the audit preview</h2><p>Recent Audit Logs shows a preview with time, user, action, and course. Select <strong>View All Logs</strong> to open the complete Audit Logs page for searching and filtering activity.</p></section>
	<section class="api-doc-section"><h2>3. Understand system status</h2><p>The dashboard displays Backend API, Database, Chat API, and Granite with a Healthy label. These labels are currently static dashboard values, not verified live health checks, so investigate issues through the relevant logs and services.</p></section>
	<section class="api-doc-section"><h2>4. Compare active courses</h2><p>Top Active Courses ranks up to five courses by recorded request events. Its progress bars compare each course’s request count with the highest displayed count; they are a relative comparison, not a utilization percentage.</p></section>
	<section class="api-doc-section"><h2>5. Continue administration</h2><p>Administrators can use the sidebar to open Users, Courses, Admin Panel, Audit Logs, API Keys, Account, Chat, and Help. Use the dashboard for an overview, then open the specific page needed for detail.</p></section>
	<section class="api-doc-section"><h2>Recommended practices</h2><ul><li>Use the dashboard for a quick overview.</li><li>Open Audit Logs for detailed activity.</li><li>Open API Keys for key management.</li><li>Open Users for account and role management.</li><li>Investigate unusual activity instead of relying only on summary cards.</li></ul></section>
</div>
