# Admin Dashboard

> **For instructors and administrators**  
> Use this guide for a quick Rocky activity overview. Estimated reading time: 2–3 minutes.

The Admin Dashboard summarizes current Rocky data and provides quick access to administrative information.

## 1. Read the dashboard overview

**Total Users** counts loaded user accounts, **Active Users** counts active accounts, and **Total Courses** counts loaded courses. **API Keys Issued** counts API-key summaries returned for those courses. **Requests Today** counts recorded request events dated today when the dashboard loads.

![Admin Dashboard showing summary cards, audit logs, system status, and top active courses](/Admin-1.Panel.png)

_The dashboard provides an overview of administrative information and activity._

## 2. Review the audit preview

Recent Audit Logs shows a preview with time, user, action, and course. Select **View All Logs** to open the complete Audit Logs page for searching and filtering activity.

## 3. Understand system status

The dashboard displays Backend API, Database, Chat API, and Granite with a Healthy label. These labels are currently static dashboard values, not verified live health checks, so investigate issues through the relevant logs and services.

## 4. Compare active courses

Top Active Courses ranks up to five courses by recorded request events. Its progress bars compare each course’s request count with the highest displayed count; they are a relative comparison, not a utilization percentage.

## 5. Continue administration

Administrators can use the sidebar to open Users, Courses, Admin Panel, Audit Logs, API Keys, Account, Chat, and Help. Use the dashboard for an overview, then open the specific page needed for detail.

## Recommended practices

- Use the dashboard for a quick overview.
- Open Audit Logs for detailed activity.
- Open API Keys for key management.
- Open Users for account and role management.
- Investigate unusual activity instead of relying only on summary cards.
