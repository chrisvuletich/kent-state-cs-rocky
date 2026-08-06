# Getting Started

An API (Application Programming Interface) allows different software applications to communicate with one another. The Rocky API lets your application securely send requests and receive data from Rocky.

## Join a class

Your instructor adds you to the course roster. Once added, the course appears in the **Courses** view. If it is missing, contact your instructor; students cannot add themselves to a course roster.

## How APIs Work

When your application needs information, it sends a request to the Rocky API. Rocky processes the request and returns a response containing the requested data.

## Request and Response

Every API interaction consists of a request sent by your application and a response returned by the server.

```
Request
    ↓
Rocky API
    ↓
Response
```

## JSON Data

The Rocky API sends and receives information using JSON (JavaScript Object Notation), a lightweight format that is easy for both people and computers to read.

```json
{
  "model": "rocky",
  "input": "Hello Rocky!"
}
```

## HTTP Methods

APIs use different HTTP methods depending on the action being performed.

- **GET** — Retrieve data.
- **POST** — Send new data.
- **PUT** — Update existing data.
- **DELETE** — Remove data.

## Course API keys

API keys are tied to a course. Open an enrolled course to generate and manage its key. Instructors can use the Course Roster Workflow in the Help Center to add students.

## Next Steps

Now that you understand the basics of APIs, you're ready to begin using the Rocky API.

- Generate your API key.
- Read the Python example.
- Explore the API Reference.
