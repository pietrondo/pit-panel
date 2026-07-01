# Host Terminal Specification

## Purpose

Provide a web-based terminal emulator connected to the host shell via WebSockets.

## Requirements

### Requirement: Admin Authentication

The WebSocket endpoint and terminal page MUST reject unauthenticated or non-admin users.

#### Scenario: Access Denied to Non-Admins
- GIVEN a user who is not logged in or is not an administrator
- WHEN requesting `/system/terminal` or connecting to `/system/terminal/ws`
- THEN the system MUST return a 401 or 403 status or redirect to login

#### Scenario: Access Granted to Admins
- GIVEN a user who is logged in as an administrator
- WHEN requesting `/system/terminal` or connecting to `/system/terminal/ws`
- THEN the system MUST allow access and establish connection

### Requirement: PTY Subprocess Execution

The system MUST spawn the host shell in a pseudo-terminal (PTY) session, executing `powershell.exe` on Windows and `/bin/bash` or `sh` on Linux.

#### Scenario: Spawn OS Shell
- GIVEN the panel is running on Windows (or Linux)
- WHEN a WebSocket connection is initiated at `/system/terminal/ws`
- THEN the backend MUST spawn `powershell.exe` (or `/bin/bash` / `sh` on Linux) as a subprocess

### Requirement: WebSocket Data Piping

The system MUST pipe the subprocess stdout and stderr to the WebSocket connection, and pipe user input from the WebSocket connection to the subprocess stdin.

#### Scenario: Pipe Data Streams
- GIVEN an active WebSocket shell session
- WHEN user keystroke data is sent via WebSocket or shell output is generated
- THEN the system MUST pipe the input to subprocess stdin and the output to WebSocket client
