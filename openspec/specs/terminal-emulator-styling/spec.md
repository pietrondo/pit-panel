# Specification: Terminal Emulator Styling

This specification defines the visual formatting and behaviors for rendering system command outputs as a stylized, retro terminal emulator.

## 1. Overview
Command outputs, server logs, and deployment logs currently shown in raw text must be wrapped inside a simulated Unix terminal emulator component to provide a cohesive, premium developer tool experience.

## 2. Requirements

### 2.1 Outer Window Container
- The emulator wrapper MUST have a slate-900 (`bg-slate-900`) or darker background.
- It MUST have rounded corners (minimum `rounded-lg`).
- It MUST include a subtle border or drop shadow (`shadow-xl`) to elevate it from the dashboard background.

### 2.2 Terminal Header Bar
- The emulator container MUST include a top control bar (header).
- The header bar MUST display three colored window control dots aligned to the left:
  - Red dot (Close button mock)
  - Yellow dot (Minimize button mock)
  - Green dot (Maximize button mock)
- The header bar SHOULD display a centered label text (e.g., "Terminal", "bash", or the active process name/status) in a muted monospace font.

### 2.3 Monospace Text Area
- The output text area MUST use a high-legibility monospace font, preferring `JetBrains Mono` or `Fira Code`.
- The text color MUST be neon green (`text-emerald-400` / `text-green-400`) or amber (`text-amber-400`) to evoke a classic CLI look.
- The terminal area MUST have vertical scrollbars automatically enabled when content overflows.
- Scrollbars MUST be custom-styled to match the dark color scheme of the terminal window (e.g., dark slate track with a muted gray scrollbar thumb).

## 3. Scenarios

### Scenario 1: Rendering Active Process Output
**GIVEN** a log or system command command is active in the dashboard
**WHEN** the system management page renders the output container
**THEN** the wrapper container MUST display the top header bar with Red, Yellow, and Green control dots
**AND** the text MUST render in neon green or amber color on a dark slate background
**AND** the font family MUST resolve to a monospace font family containing JetBrains Mono, Fira Code, or generic monospace.

### Scenario 2: Auto-Scrolling on New Output Lines
**GIVEN** an active log stream inside the terminal component
**WHEN** new lines of logs are appended to the console
**THEN** the scroll area SHOULD automatically scroll to the bottom to display the latest updates
**AND** if vertical content exceeds the container height, a custom styled dark scrollbar MUST become visible.
