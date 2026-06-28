# OpenSpec for pit-panel

This directory holds the specifications, design proposals, implementation tasks, and changes for the `pit-panel` project using Spec-Driven Development (SDD).

## Directory Structure

- [config.yaml](file:///C:/Users/pietr/progetti/pit-panel/openspec/config.yaml): Core configuration for SDD including tech stack, testing, and agent rules.
- `specs/`: Directory for product specifications and feature designs.
- `changes/`: Directory for active and archived changes (each change has its own folder containing proposals, specs, tasks, etc.).

## SDD Workflow Commands

- `/sdd-init`: Initialize or refresh the SDD context.
- `/sdd-new <change>`: Start a new feature or bug fix.
- `/sdd-explore <topic>`: Investigate a concept or codebase pattern.
- `/sdd-apply`: Implement code changes defined in the tasks.
- `/sdd-verify`: Validate the implementation against specs and run test suites.
- `/sdd-archive`: Archive the change once it is completed and merged.
