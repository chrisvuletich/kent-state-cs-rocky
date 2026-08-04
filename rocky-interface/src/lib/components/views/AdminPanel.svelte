<script lang="ts">
  import "$lib/styles/components/modules/admin-panel.css";
  import { onMount } from "svelte";
  import { fetchUsersForViews } from "$lib/api/users";
  import { fetchCourses } from "$lib/api/content";
  import { fetchCourseApiHistory, fetchCourseApiKeys } from "$lib/api/courses";
  import { currentFrame } from "$lib/stores/frameStore";

  import {
    IconUsers,
    IconBooks,
    IconKey,
    IconActivityHeartbeat,
    IconShieldCheck,
    IconChartBar,
    IconListDetails
  } from "@tabler/icons-svelte";

  let stats = [
    { title: "Total Users", value: "—", icon: IconUsers },
    { title: "Active Users", value: "—", icon: IconUsers },
    { title: "Total Courses", value: "—", icon: IconBooks },
    { title: "API Keys Issued", value: "—", icon: IconKey },
    { title: "Requests Today", value: "—", icon: IconActivityHeartbeat }
  ];

  function formatActivityTime(timestamp: string): string {
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
  }

  onMount(async () => {
    try {
      const [users, courses] = await Promise.all([fetchUsersForViews(), fetchCourses()]);
      const courseApiKeys = await Promise.all(courses.map((course) => fetchCourseApiKeys(course.id)));
      stats[0] = { ...stats[0], value: String(users.length) };
      stats[1] = { ...stats[1], value: String(users.filter((user) => user.isActive).length) };
      stats[2] = { ...stats[2], value: String(courses.length) };
      stats[3] = { ...stats[3], value: String(courseApiKeys.reduce((total, keys) => total + keys.length, 0)) };
      const courseActivity = await Promise.all(courses.map((course) => fetchCourseApiHistory(course.id)));
      const activityEntries = courseActivity.flat();
      const today = new Date().toDateString();
      stats[4] = { ...stats[4], value: String(activityEntries.filter((event) => event.eventType === "request" && new Date(event.created).toDateString() === today).length) };
      const peopleByIdentifier = new Map(users.flatMap((user) => [[user.id.toLowerCase(), user], [user.email.toLowerCase(), user]]));
      const displayUser = (identifier: string) => {
        const user = peopleByIdentifier.get(identifier.toLowerCase());
        return user ? `${user.displayName} (${user.email})` : identifier;
      };
      audit = activityEntries.slice(0, 5).map((event) => ({
        time: formatActivityTime(event.created),
        user: displayUser(event.userId),
        action: event.eventType.replace(/-/g, " "),
        course: event.courseCode
      }));
      const requestCounts = activityEntries.reduce((counts, event) => {
        if (event.eventType === "request") {
          counts.set(event.courseCode, (counts.get(event.courseCode) || 0) + 1);
        }
        return counts;
      }, new Map<string, number>());
      const highestRequestCount = Math.max(...requestCounts.values(), 1);
      topCourses = [...requestCounts.entries()]
        .sort(([, firstRequests], [, secondRequests]) => secondRequests - firstRequests)
        .slice(0, 5)
        .map(([name, requests]) => ({ name, requests, width: `${(requests / highestRequestCount) * 100}%` }));
    } catch (err) {
      console.error("[admin panel] failed to load dashboard totals", err);
    }
  });

  const services = [
    { name: "Backend API", status: "Healthy" },
    { name: "Database", status: "Healthy" },
    { name: "Chat API", status: "Healthy" },
    { name: "Granite", status: "Healthy" }
  ];

  let topCourses: { name: string; requests: number; width: string }[] = [];

  let audit: { time: string; user: string; action: string; course: string }[] = [];
</script>

<div class="admin-panel">
  <div class="header">
    <div>
      <h1>Admin Dashboard</h1>
      <p>Monitor users, courses, API usage, and overall Rocky system activity.</p>
    </div>
  </div>

  <section class="stats-grid">
    {#each stats as stat}
      <div class="panel-card stat-card">
        <svelte:component this={stat.icon} size={28}/>
        <div class="stat-value">{stat.value}</div>
        <div class="stat-title">{stat.title}</div>
      </div>
    {/each}
  </section>

  <section class="admin-content-grid">
    <section class="panel-card audit-section">
      <div class="card-header">
        <IconListDetails size={20}/>
        <h2>Recent Audit Logs</h2>
        <button type="button" onclick={() => currentFrame.set('audit')}>View All Logs</button>
      </div>

      <div class="admin-audit-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>User</th>
            <th>Action</th>
            <th>Course</th>
          </tr>
        </thead>

        <tbody>
          {#each audit as row}
            <tr>
              <td>{row.time}</td>
              <td>{row.user}</td>
              <td>{row.action}</td>
              <td>{row.course}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      </div>
    </section>

    <aside class="admin-side-stack">
      <section class="panel-card">
        <div class="card-header">
          <IconShieldCheck size={20}/>
          <h2>System Status</h2>
        </div>

        {#each services as service}
          <div class="status-row">
            <span>{service.name}</span>
            <span class="healthy">{service.status}</span>
          </div>
        {/each}
      </section>

      <section class="panel-card">
        <div class="card-header">
          <IconChartBar size={20}/>
          <h2>Top Active Courses</h2>
        </div>

        {#each topCourses as course}
          <div class="course-row">
            <div class="course-top">
              <span>{course.name}</span>
              <span>{course.requests} requests</span>
            </div>

            <div class="progress">
              <div class="fill" style={`width:${course.width}`}></div>
            </div>
          </div>
        {/each}
      </section>
    </aside>
  </section>
</div>
