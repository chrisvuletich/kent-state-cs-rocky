# User Management

> **For administrators**
> Use this guide to manage Rocky accounts. Estimated reading time: 2–3 minutes.

User Management helps administrators find accounts, review identity and status, update roles, and safely manage account access in bulk. Instructors manage students enrolled in their courses from the course roster instead.

## 1. Choose an account source

Use **Kent accounts** to work with accounts using Kent email addresses. Use **Whitelist accounts** to review the separate approved-account list and add a whitelist entry when needed. Choose the new account's Student, Instructor, or Admin role when adding it; that role is applied on the account's first Microsoft login.

![Kent accounts and Whitelist accounts tabs on the User Management page](/UM-1.Acc-Source.png)

_Administrators can switch between the two account sources._

## 2. Search, filter, and sort

Search by name or email, then combine the role, status, and course filters to narrow the list. The course filter uses actual course membership or instructor and teaching-assistant associations. Choose **Name: A–Z** or **Name: Z–A** to sort the filtered results; all controls can be combined.

![Search, role, status, course, and name-sort controls on the User Management page](/UM-2.Search-Filter.png)

_Use the controls together to find the accounts you need._

## 3. Review the user table

The table shows a selection checkbox, name, email, role, status, and actions. Use the first checkbox to select all users currently visible after filtering.

## 4. Update roles carefully

Choose **Student**, **Instructor**, or **Admin** from the role dropdown. Rocky asks for confirmation before changing a role and provides feedback after the update. Verify the account identity before changing permissions.

![Role selectors in the Actions column of the current User Management table](/UM-4.Role-Dropdown.png)

_Confirm the correct account before changing permissions._

## 5. Activate, deactivate, and use bulk actions

**Active** accounts can use Rocky; **Inactive** accounts cannot. Deactivation also suspends API keys owned by that account. Use the row action to deactivate or reactivate one account. For several accounts, select rows, use the bulk toolbar, and confirm the change. Rocky reports updated accounts and any selected accounts that could not be found.

![Selected user accounts and bulk activation controls on the User Management page](/UM-5.Bulk-Activate.png)

_Select rows or use select all before confirming a bulk activation or deactivation._

## Recommended practices

- Verify a user’s identity before changing a role.
- Avoid deactivating active instructors during a current term without confirmation.
- Use filters before applying a bulk action.
- Review the result message after each bulk operation.
