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

Administrators can use the sidebar to open Analytics, Users, Courses, Admin Panel, Audit Logs, API Keys, Account, Chat, and Help. Use the dashboard for an overview, then open the specific page needed for detail.

## 6. Inspect AI usage analytics

Open **Analytics** to review live AI request telemetry. Choose a time window to compare request and token throughput, model speed, outcomes, latency, and rate-limit activity. **Rate-limit rejections** count normal `429` enforcement events; **Limiter unavailable** identifies operational failures that prevented a rate-limit decision. Use the error-type filter to inspect the matching requests, including `rate_limit_exceeded`, `rate_limit_unavailable`, and `rate_limit_identity_unavailable`. Use **Breakdown** to group the same metrics by user, course, API key, group, model, request source, or outcome.

The **Review queue** opens the complete recorded prompt and response text. This conversation content is retained verbatim and is not sanitized. Filter it by request outcome, error type, flagged state, or review status to focus on requests that need attention. Request details show the error stage and type when the request failed or was rejected. Analytics and review controls are restricted to administrators.

For a request that needs follow-up, mark it **Flagged**, choose at least one structured reason, set its status to **Unreviewed**, **In review**, or **Resolved**, and add concise administrative notes. Saving records the reviewing administrator and time. Removing the flag also removes its flag reasons, while notes and workflow status remain available for documenting the decision.

Every saved review appends the previous and updated review values to the request's history and creates a metadata-only audit event. The audit event identifies the request and review transition; it does not create another copy of the prompt or response. Authentication material—including plaintext API keys, authorization headers, cookies, internal service tokens, and stored key hashes—is excluded independently from the verbatim conversation record.

If another administrator saves the same review first, Rocky preserves your
draft and asks you to reload the newer review instead of overwriting it.

The **Hardware & model correlation** section aligns Granite GPU utilization,
VRAM use, generation speed, and p95 request latency over the selected window.
Its latest strip also shows GPU temperature, CPU/RAM use, and Rocky's current
active-request count. Requests that never reached a terminal state and are more
than four minutes old are shown separately as unresolved rather than active. A
**Partial**, **Stale**, or **Unavailable** state means the dashboard
does not have a complete recent Granite snapshot; it must not be interpreted as
zero utilization. The source hostname identifies which machine was measured.

## Recommended practices

- Use the dashboard for a quick overview.
- Open Audit Logs for detailed activity.
- Open API Keys for key management.
- Open Users for account and role management.
- Investigate unusual activity instead of relying only on summary cards.
