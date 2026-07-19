<script lang="ts">
    import "$lib/styles/components/modules/admin-panel.css";

    interface AdminCard {
        title: string;
        description: string;
        status: string;
        enabled: boolean;
    }

    const cards: AdminCard[] = [
        {
            title: "User Management",
            description: "View and manage Rocky users, permissions, and account status.",
            status: "Available",
            enabled: true
        },
        {
            title: "System Logs",
            description: "Review login activity, API usage, and system events.",
            status: "Coming Soon",
            enabled: false
        },
        {
            title: "API Keys",
            description: "Manage user API keys and monitor usage.",
            status: "Coming Soon",
            enabled: false
        },
        {
            title: "Settings",
            description: "Configure Rocky administration settings.",
            status: "Coming Soon",
            enabled: false
        }
    ];

    function openCard(card: AdminCard) {
        if (!card.enabled) return;

        switch (card.title) {
            case "User Management":
                // TODO: Switch to UsersView
                console.log("Open Users");
                break;
        }
    }
</script>

<div class="admin-panel">
    <div class="header">
        <h1>Admin Panel</h1>
        <p>
            Administrative tools for managing Rocky and monitoring system
            activity.
        </p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <span class="stat-number">1</span>
            <span class="stat-label">Available Tool</span>
        </div>

        <div class="stat-card">
            <span class="stat-number">3</span>
            <span class="stat-label">Planned Tools</span>
        </div>
    </div>

    <div class="cards">
        {#each cards as card}
            <button
                class:disabled={!card.enabled}
                class="tool-card"
                on:click={() => openCard(card)}
            >
                <div class="card-top">
                    <h2>{card.title}</h2>

                    <span
                        class:available={card.enabled}
                        class:coming={!card.enabled}
                        class="status"
                    >
                        {card.status}
                    </span>
                </div>

                <p>{card.description}</p>
            </button>
        {/each}
    </div>
</div>