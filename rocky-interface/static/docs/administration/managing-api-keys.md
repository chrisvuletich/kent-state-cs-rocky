# Managing API Keys

> **For administrators**
> Use this guide to manage course API-key access safely. Estimated reading time: 2–3 minutes.

The API Keys page lets administrators manage keys across Rocky without exposing secret key values. Instructors manage keys for their own courses from the Courses workspace.

## 1. Review safe key information

Full API key values are never displayed. The page shows only the key name, owner, course, status, and creation date. Do not include internal IDs, hashes, or secret values in screenshots or documentation.

![The main administrative API Keys management view](/API-1.Full-Page.png)

_The main administrative API key view shows safe key-management information._

## 2. Search and filter

Search by owner, email, key name, or course. Combine the status, semester, and course filters as needed. Selecting a semester narrows the course list to that term. Use the sortable column headings when you need a different organization.

![Search, status, semester, and course filters on the API Keys management page](/API-2.Filter.png)

_Filters can be combined before sorting the results._

## 3. Sort and review keys

Keys start with newer semesters first, then course and owner. Select the Semester, Course, Owner, Status, or Created column heading to sort; the active heading shows the sort direction.

The table includes selection, semester, owner, role or owner type, course, key name, status, created date, and actions. Group-owned keys may show a group identifier instead of a person’s name.

## 4. Read status safely

Active rows have a subtle green tint and inactive rows have a subtle red tint. The Active or Inactive badge remains visible, so status does not depend on color alone.

![API key rows with visible status badges and supporting row tint](/API-4.Tint.png)

_Row color supports the visible status badge rather than replacing it._

## 5. Change key status

Use **Deactivate** or **Reactivate** for one key and confirm the prompt. Prefer deactivation over permanent deletion when historical records may still refer to the key.

## 6. Use bulk actions

Select multiple keys or use the select-all checkbox for the visible filtered rows. Bulk deactivate and reactivate actions ask for confirmation. Use **Clear selection** to start over. Keys already in the requested state are skipped, and the completion message reports successes, failures, and skipped keys.

![Bulk API key action toolbar with deactivate, reactivate, and clear selection controls](/API-6.BulkBar.png)

_Bulk actions apply only to the keys selected in the current filtered results._

## Recommended practices

- Filter to the correct semester and course before bulk actions.
- Confirm the owner and course before changing a key.
- Deactivate keys that should no longer be usable.
- Never copy or expose secret values.
