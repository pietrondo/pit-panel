# Specification: App List Interface

This specification defines the design, functional structure, and user interaction rules for the primary application dashboard interface.

## 1. Overview
The `/apps` dashboard allows users to view, manage, and deploy applications. This interface must present real-time container states, stack selections, and deploy status feedback using lightweight async updates and modern hover animations.

## 2. Requirements

### 2.1 Application Status Dashboard
- The application grid/table MUST display each app subdomain with its current state.
- For each app, the list view MUST display an active/inactive status indicator badge:
  - Active (green badge): at least one container in the stack is running.
  - Inactive (gray/red badge): no containers in the stack are currently running.
- The interface MUST display the count of running containers versus the total defined containers in the stack (e.g., `2/3 running` or `0/1 running`).
- These container statistics SHOULD be retrieved asynchronously or dynamically to avoid blocking the initial page load.

### 2.2 Stack Selection Cards
- The creation/deployment screen MUST feature stack choice cards.
- The stack cards MUST include micro-animations on interaction:
  - Transition scale on hover (e.g., scale up slightly by `102%`).
  - Smooth shadow transitions and glow borders on focus/hover.
- Each card MUST display the corresponding stack icon/badge (e.g., Python, Docker, Node.js, Static).

### 2.3 Deploy Feedback UI
- When a user triggers a deployment or stack update, the user interface MUST display a loading indicator or stepper (e.g., "Deploying...", "Pulling images...", "Starting containers").
- The deploy button and stack selection MUST disable inputs during an active deployment operation to prevent duplicate execution.
- The feedback MUST utilize HTMX indicator classes (`htmx-indicator`) to seamlessly show/hide progress spinners.

## 3. Scenarios

### Scenario 1: Displaying App State and Container Counts
**GIVEN** an application subdomain "blog" has a docker-compose stack with 3 defined containers, where 2 are running
**WHEN** the user visits the `/apps` dashboard list view
**THEN** the list MUST display an active badge (green) for "blog"
**AND** the container status column MUST display "2/3 running"

### Scenario 2: Selecting a Stack Card with Interactive Feedback
**GIVEN** the user is viewing the "Create App" form
**WHEN** the user hovers over a stack selection card
**THEN** the card MUST scale up smoothly with a transition duration of at least 150ms
**AND** it MUST glow or darken its borders to signify interactivity

### Scenario 3: HTMX Deploy Indicator Feedback
**GIVEN** the user is initiating a stack deploy
**WHEN** the deploy form is submitted via HTMX
**THEN** the submit button and active select boxes MUST be disabled
**AND** the HTMX progress indicator spinner MUST be visible to show deployment progress
