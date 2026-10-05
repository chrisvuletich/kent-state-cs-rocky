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
