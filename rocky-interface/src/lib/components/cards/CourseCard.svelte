<script lang="ts">
  import '$lib/styles/components/modules/course-card.css';
  import '$lib/styles/components/modules/view-controls.css';
  import { createEventDispatcher } from 'svelte';
  
  export let course: {
    id: number;
    code: string;
    name: string;
    instructor: string;
    semester: string;
    color: string;
  };
  export let mode: 'card' | 'list' = 'card';
  export let roleTag = '';

  const dispatch = createEventDispatcher<{ open: { courseId: number } }>();

  function openCourse() {
    dispatch('open', { courseId: course.id });
  }

  $: courseHexColor = course.color?.trim() || '#334155';
  $: courseCodeLabel = course.code?.trim() || '';
  $: courseInstructorLabel = course.instructor?.trim() || '';
  $: courseSemesterLabel = course.semester?.trim() === 'None' ? '' : course.semester?.trim() || '';
  $: courseMetaLabel = [courseInstructorLabel, courseCodeLabel, courseSemesterLabel].filter((value) => value.length > 0).join(' · ');
</script>

{#if mode === 'card'}
  <div class="course-card" role="button" tabindex="0" on:click={openCourse} on:keydown={(event) => (event.key === 'Enter' || event.key === ' ' ? openCourse() : null)}>
    <div class="card-banner" style={`background-color: ${courseHexColor};`}>
      {#if roleTag}
        <p class="course-role-tag course-role-tag-banner">{roleTag}</p>
      {/if}
    </div>
    <div class="card-body">
      <p class="course-name">{course.name}</p>
      {#if courseMetaLabel}
        <p class="course-meta">{courseMetaLabel}</p>
      {/if}
    </div>
    <div class="card-footer">
      <button type="button" class="go-btn" on:click|stopPropagation={openCourse}>Go to Course →</button>
    </div>
  </div>
{:else}
  <div class="list-row" role="button" tabindex="0" on:click={openCourse} on:keydown={(event) => (event.key === 'Enter' || event.key === ' ' ? openCourse() : null)}>
    <div class="list-color-bar" style={`background-color: ${courseHexColor};`}></div>
    <div class="list-course-icon" style={`background-color: ${courseHexColor};`}>
      {courseCodeLabel.slice(0, 2)}
    </div>
    <div class="list-info">
      <p class="list-course-name">{course.name}</p>
      {#if courseMetaLabel}
      <p class="list-course-meta">{courseMetaLabel}</p>
      {/if}
      {#if roleTag}
        <p class="course-role-tag course-role-tag-list">{roleTag}</p>
      {/if}
    </div>
    <button type="button" class="list-go-btn" on:click|stopPropagation={openCourse}>Go →</button>
  </div>
{/if}
