<script lang="ts">
  import "$lib/styles/components/modules/admin-panel.css";

  import {
    IconUsers,
    IconBooks,
    IconKey,
    IconActivityHeartbeat,
    IconShieldCheck,
    IconClock,
    IconChartBar,
    IconListDetails
  } from "@tabler/icons-svelte";

  const stats = [
    { title: "Total Users", value: "27", icon: IconUsers },
    { title: "Total Courses", value: "6", icon: IconBooks },
    { title: "API Keys Issued", value: "42", icon: IconKey },
    { title: "Requests Today", value: "1,248", icon: IconActivityHeartbeat },
    { title: "System Health", value: "Healthy", icon: IconShieldCheck }
  ];

  const activity = [
    { action: "John Smith logged in", time: "2 minutes ago" },
    { action: "CS49000 created", time: "15 minutes ago" },
    { action: "API key generated", time: "24 minutes ago" },
    { action: "Instructor added to course", time: "42 minutes ago" },
    { action: "Admin updated permissions", time: "1 hour ago" }
  ];

  const services = [
    { name: "Backend API", status: "Healthy" },
    { name: "Database", status: "Healthy" },
    { name: "Chat API", status: "Healthy" },
    { name: "Granite", status: "Healthy" }
  ];

  const courses = [
    { name: "CS49000", requests: 320, width: "100%" },
    { name: "CS33901", requests: 240, width: "75%" },
    { name: "CS23021", requests: 150, width: "45%" }
  ];

  const audit = [
    { time: "10:35", user: "John Smith", action: "Login", course: "-" },
    { time: "10:32", user: "Admin", action: "Created Course", course: "CS49000" },
    { time: "10:18", user: "Jane Doe", action: "Generated API Key", course: "CS33901" }
  ];
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

  <section class="dashboard-grid">
    <div class="panel-card">
      <div class="card-header">
        <IconClock size={20}/>
        <h2>Recent Activity</h2>
      </div>

      {#each activity as item}
        <div class="activity-row">
          <div>
            <strong>{item.action}</strong>
            <p>{item.time}</p>
          </div>
        </div>
      {/each}
    </div>

    <div class="panel-card">
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
    </div>

    <div class="panel-card">
      <div class="card-header">
        <IconChartBar size={20}/>
        <h2>Top Active Courses</h2>
      </div>

      {#each courses as course}
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
    </div>
  </section>

  <section class="panel-card audit-section">
    <div class="card-header">
      <IconListDetails size={20}/>
      <h2>Recent Audit Logs</h2>
      <button>View All Logs</button>
    </div>

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
  </section>
</div>
