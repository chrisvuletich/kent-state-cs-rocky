# Course Roster Workflow

After creating a course, use the roster tools to add students individually or import the full class from Canvas.

## 1. Open your course roster

Open **Courses**, select your course, then choose **Edit Roster**.

![The Edit Roster tab in the current course workspace](/class_doc_1.png)

## 2. Add a student manually

On the Edit Roster tab, click **Add Email**.

![The Add Email and Import Canvas CSV controls on the current Edit Roster page](/class_doc_2.png)

## 3. Enter the student’s email

Enter the student’s Kent email address, then select **Add User**.

![The Kent email field in the Add User by Email dialog](/class_doc_3.png)

## 4. Import a Canvas roster

To add the full class at once, select **Import Canvas CSV** and upload the roster exported from Canvas.

In Canvas, open your course, select **Course Analytics** (sometimes labeled
**New Analytics**), then **Reports**. Run the **Class Roster** report and
download its CSV file.

Rocky reads the **Email** column. A typical export looks like this:

```csv
Student Name,Student ID,Student SIS ID,Email,Section Name
Example Student,123456,,student@kent.edu,Fall 2026 SOFTWARE ENGINEERING
```

Blank SIS IDs are fine; Canvas student IDs and SIS IDs are not used to match
Rocky accounts. Other columns may appear in any order. A CSV containing just
an **Email** column also works. Students can be added before their first Rocky
login; their accounts are linked by email when they sign in.

Duplicate emails are combined, existing roster members are updated without
creating duplicates, and known admin accounts are excluded. The import shows
a confirmation with the number of unique emails processed. Empty files,
missing Email columns, malformed CSV, and student rows with missing or invalid
emails show an error without importing any students. Correct the file and
select it again to retry.

![The current Edit Roster page with the Import Canvas CSV control above the roster](/class_doc_2.png)

## 5. Set student key allowances

The **Keys** column controls how many individual API-key slots each student may
use in this course. Enter the allowed number and select **Save**. The value
cannot exceed the course-wide student limit. A closed course is read-only, so
reopen it before changing a roster or key allowance.

## 6. Confirm the roster

Added students appear in the roster table with their name, email, role, key
allowance, and available actions.

![An added student displayed in the course roster table](/class_doc_1.png)

## 7. Assign students to groups

Open **Groups**, create a group if needed, then select its **Add students**
button. Search by name or email and check the students you want to add.
**Select all matching** selects the eligible students in the current search;
selections stay checked when you change the search. **Clear selection** clears
all selections, including ones hidden by the search.

Students already in the group are marked **Already in group** and cannot be
selected again. Students who have not signed in yet may show **Pending user**;
use their email address to identify them. Course instructors and teaching
assistants are not included in this student picker. Students can belong to more
than one group.

Select **Add N students** to save the full selection together. The confirmation
reports how many students were actually added. If the request fails, the dialog
keeps your selection and displays an error. If the roster changed and a selected
student was removed, cancel, refresh the course, and reopen the dialog before
trying again. Repeating a successful selection does not create duplicates.

Group assignment is available to course instructors, teaching assistants, and
admins. Closed courses must be reopened before editing. The Add students dialog
does not turn on self-joining; use the separate setting below.

## 8. Let students join groups themselves

Self-joining is **off by default**, including for existing groups. In **Groups**,
select a group's **Settings**, enable **Allow students to join
themselves**, and select **Save settings**. Instructors, course teaching
assistants, and admins can manage this setting.

Optionally enter **Maximum students**, or leave it blank for no limit. The limit
also applies to staff's Add students action and cannot be set below the current
membership count. When classmates join at the same time, Rocky checks the latest
membership before saving so they cannot both take the last seat.

Enrolled students can open **Courses → their course → Groups** and select
**Join group** for an open group. They cannot enroll themselves in the course,
join on behalf of someone else, or join a full or paused group or a closed course. Joining
is recorded durably with the membership change. If the audit log is temporarily
unavailable, its entry is delivered on a later group request or audit-log read
without duplicating the join. Students may belong to multiple groups.

Turning self-joining off stops new joins without removing existing members.
Students must contact staff to leave or switch groups: removal remains a staff
action and revokes the group's shared keys. **Removing someone from a group
does not block them from rejoining while self-joining stays on.** Disable it first
if you do not want a removed student to rejoin.

If settings change while someone has the page open, use **Refresh groups** or
refresh the course. Failed saves show an error instead of overwriting a newer
membership update. Joining never generates, regenerates, or reveals a shared
API key; instructors still manage and distribute those keys.

## 9. Manage existing groups

The single **Groups** tab contains membership, settings, and shared-key management.
Select **View group** for a group's members, shared API keys,
and settings. Students see **Your groups** first and can view their group's key
status in the same tab; only staff can generate, disable, or remove shared keys.

- **Group settings** changes the name, self-joining option, maximum students,
  and shared-key allowance. Renaming preserves the group's identity, memberships,
  and existing keys. The key allowance cannot exceed the course maximum.
- **Close joining** stops new student self-joins without changing memberships
  or shared-key access. Staff can still add students. **Open joining** enables
  self-joining subject to capacity, group pause, and course status.
- **Pause group** temporarily disables shared group keys and prevents new
  self-joins. Staff can still edit the group. **Resume group** restores access
  within the current key allowance, but never restores separately disabled or
  revoked keys. The saved self-joining setting is preserved.
- **Remove** asks for confirmation before removing a student. All the group's
  shared keys are revoked because the removed student may have copied them.
  Generate and distribute new keys to the remaining members afterward.
- **Delete group** works even when the group has members. It permanently removes
  the group and invalidates all its shared keys. Students remain enrolled in the
  course; audit and usage history are retained. Creating another group with the
  same name does not restore the deleted group's keys or memberships.

Group pause and deletion do not disable personal keys, accounts, or normal chat.
Closed courses remain read-only until reopened by an admin. If a save conflicts
with another change, use **Refresh groups**, review the latest state, and retry.
