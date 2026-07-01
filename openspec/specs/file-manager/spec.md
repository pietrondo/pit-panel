# File Manager Specification

## Purpose

Provide a system-wide web-based file manager to browse, read, write, upload, create, and delete files/folders safely.

## Requirements

### Requirement: Safety Guards and Validation

The system MUST validate all path parameters and MUST prevent path traversal or access outside the configured base directory.

#### Scenario: Block Path Traversal
- GIVEN an admin user requesting an operation on a path containing `..` or escaping `/opt/pit-panel`
- WHEN the system processes the path parameter
- THEN the system MUST reject the request with a 400 Bad Request error

### Requirement: Directory Browsing

The system MUST list files and directories inside the requested folder including their name, size, type (file or directory), and modification time.

#### Scenario: List Directory Contents
- GIVEN a valid folder path inside `/opt/pit-panel`
- WHEN the user requests to browse the folder
- THEN the system MUST return a list containing all children with their metadata

### Requirement: File CRUD Operations

The system MUST support reading and writing text/code files, creating new files/directories, and deleting files/directories.

#### Scenario: Read and Write File
- GIVEN a valid file path inside `/opt/pit-panel`
- WHEN the user reads or saves modifications to the file
- THEN the system MUST read from or securely write changes to the disk

#### Scenario: Create and Delete Resources
- GIVEN a target parent directory inside `/opt/pit-panel`
- WHEN the user creates a new file/directory or deletes an existing one
- THEN the system MUST execute the creation or deletion on the filesystem

### Requirement: File Upload

The system MUST support uploading files to a specified directory via multipart form data.

#### Scenario: Upload File
- GIVEN a target directory inside `/opt/pit-panel`
- WHEN the user uploads a file using a multipart request
- THEN the system MUST save the uploaded file to that target directory
