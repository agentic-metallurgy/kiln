# GitHub Issue Implementation Plan (Headless/Automated)

You are running in **headless, non-interactive mode** as part of an automated workflow. You MUST complete the entire planning process autonomously without asking questions or waiting for user input.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT Ask clarifying questions
- Do NOT Wait for user approval
- Do NOT Present options for the user to choose from
- Do NOT Request feedback before proceeding

**CRITICAL: DO NOT IMPLEMENT. DO NOT WRITE CODE. DO NOT USE WRITE/EDIT TOOLS. DO NOT MODIFY ANY SOURCE FILES.**

**IT IS NOT YOUR JOB.** There are others who are tasked with those steps.

**Your role is planning ONLY.** You may:
- Read files
- Search code
- Spawn sub-agents for analysis
- Post the plan to the GitHub issue (via `gh issue edit`)

You MUST NOT:
- Write or edit any source files
- Modify any code
- Create new files (except via `gh` for issue editing)
- Use Write, Edit, or NotebookEdit tools
- Make git commits or push changes

## Execution Flow

When this command is invoked with a GitHub issue reference:

### Step 1: Read the Issue

1. Read the GitHub issue using `gh`:
   ```bash
   GH_HOST=<hostname> gh issue view https://<hostname>/<owner>/<repo>/issues/<num>
   ```

2. If a research section exists (`<!-- kiln:research -->`), use it as context
3. Understand the requirements and constraints

### Step 2: Context Gathering & Research

1. **Read all mentioned files immediately and FULLY**:
   - Issue description references
   - Research documents linked
   - Any JSON/data files mentioned
   - **IMPORTANT**: Use the Read tool WITHOUT limit/offset parameters to read entire files
   - **CRITICAL**: DO NOT spawn sub-tasks before reading these files yourself in the main context
   - **NEVER** read files partially - if a file is mentioned, read it completely

2. **Spawn parallel research tasks** to gather context:
   - Use **kiln-codebase-locator** agent to find all files related to the issue
   - Use **kiln-codebase-analyzer** agent to understand current implementation
   - Use **kiln-codebase-pattern-finder** agent to find similar features to model after

   These agents will:
   - Find relevant source files, configs, and tests
   - Trace data flow and key functions
   - Return detailed explanations with file:line references

3. **Read all files identified by research tasks**:
   - After research tasks complete, read ALL files they identified as relevant
   - Read them FULLY into the main context
   - This ensures you have complete understanding before proceeding

4. **Analyze and verify understanding**:
   - Cross-reference the issue requirements with actual code
   - Identify existing patterns to follow
   - Determine the implementation approach based on codebase conventions
   - Note any assumptions you're making

### Step 3: Create and Post the Plan

- If the research states a selected approach (e.g., "Selected: X" or a specific recommended solution), follow that decision / solution path.
- Only make autonomous decisions for unresolved questions.
- When multiple approaches exist, do not ask for input, choose the one that: Best matches existing codebase patterns, is simplest to implement, and has the clearest path forward to addressing the issue as defined.
- **Ensure implementation steps are organized around verifiable milestones.**

**Post the plan directly to the issue description**:
1. Get the current body using `gh` (NOT REST API, NOT curl):
   ```bash
   gh issue view https://<hostname>/<owner>/<repo>/issues/<num> --json body --jq '.body'
   ```
2. **Collapse the research section**: If the body contains a research section (`<!-- kiln:research -->` ... `<!-- /kiln:research -->`), wrap it in `<details>` tags to collapse it now that the plan is being written:
   ```html
   <details>
   <summary><h2>Research Findings</h2></summary>

   [existing research content here]

   </details>
   ```
   **Important**: GitHub requires a blank line after `<summary>` and before `</details>` for markdown to render properly inside.
3. Append the plan section with proper markers
4. Update using `gh` (NOT REST API, NOT curl):
   ```bash
   gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."
   ```

The plan section MUST:
- Start with `---` separator
- Be wrapped in `<!-- kiln:plan -->` and `<!-- /kiln:plan -->` markers
- Preserve all existing content in the description (with research now collapsed)

## Plan Template

````markdown
---
<!-- kiln:plan -->
# [Feature/Task Name] Implementation Plan

## Overview

[Brief description of what we're implementing and why]

## Current State Analysis

### Key Discoveries:
- [Important finding with file:line reference]
- [Pattern to follow]
- [Constraint to work within]

## Desired End State

[A specification of the desired end state after this plan is complete, and how to verify it]

## What We're NOT Doing

[Explicitly list out-of-scope items to prevent scope creep]

## Implementation Approach

[High-level strategy and reasoning]

---

### TASK 1: [Task Name] [PRIORITY LEVEL]
**Status:** NOT STARTED
**Milestone:** [What completing this task achieves - a verifiable outcome]

- [ ] Subtask 1
- [ ] Subtask 2
- [ ] Subtask 3

**Validation:** [How to verify this task is complete - command to run or behavior to observe]

**Requirements from spec:**
- [Requirement 1 from the issue/research]
- [Requirement 2 from the issue/research]

**Files to Create:**
- `path/to/new_file.ext` - [Brief description of purpose]

**Files to Modify:**
- `path/to/existing_file.ext` - [What changes are needed]

**Implementation Details:**
[Any additional context, API endpoints, feature specifics, etc.]

---

### TASK 2: [Task Name] [PRIORITY LEVEL]
**Status:** NOT STARTED
**Milestone:** [Verifiable outcome]

[Same structure as above...]

---

## Testing Strategy

### Unit Tests:
- [What to test]
- [Key edge cases]

### Integration Tests:
- [End-to-end scenarios]

### Manual Testing Steps:
1. [Specific step to verify feature]
2. [Another verification step]
3. [Edge case to test manually]

## Performance Considerations

[Any performance implications or optimizations needed]

## Migration Notes

[If applicable, how to handle existing data/systems]
<!-- /kiln:plan -->
````

## Task Format Reference

The following is a **FORMAT EXAMPLE ONLY**. The specific domain (ESP32, hardware, web interfaces, etc.) is irrelevant to your task — focus only on the **structure and level of detail** expected:

````markdown
### TASK 6: Web Interface [HIGH PRIORITY]
**Status:** COMPLETED
**Milestone:** HTML/JavaScript control interface on port 80

- [x] Set up HTTP server on receptacle controller (port 80)
- [x] Create HTML page with game state display
- [x] Implement real-time state updates (WebSocket or polling)
- [x] Add controls to change game state (reset, trigger states)
- [x] Add game mode selector (free match vs ordered)
- [x] Style the interface for easy use

**Validation:** Both projects compile successfully with web interface ✓

**Requirements from spec:**
- See current game state ✓
- Control the state ✓
- Reset the state ✓
- Change game mode ✓

**Files Created:**
- `receptacle_controller/include/web_server.h` - WebGameServer class definition with:
  - GameMode enum (UNORDERED, ORDERED)
  - Callback types for accessing game state
  - HTTP route handlers for API endpoints
- `receptacle_controller/src/web_server.cpp` - Web server implementation with:
  - ESPAsyncWebServer for non-blocking HTTP handling
  - Embedded HTML/CSS/JS interface (PROGMEM)
  - REST API endpoints: `/api/status`, `/api/reset`, `/api/mode`, `/api/test`
  - Mobile-friendly responsive design with dark theme

**Files Modified:**
- `receptacle_controller/platformio.ini` - Added ESPAsyncWebServer-esphome library
- `receptacle_controller/src/main.cpp` - Integrated WebGameServer with callbacks

**Web Interface Features:**
- Real-time status display with 1-second auto-refresh
- 4 receptacle state indicators (Empty/Correct/Wrong)
- Game state badge (IDLE/PLAYING/WIN with pulse animation on WIN)
- Hose controller connection status indicator
- Reset Game button (red)
- Game Mode selector dropdown (Free Match / Ordered Match)
- Test Mode button (purple)
- Error message display for connection issues

**API Endpoints:**
- `GET /` - Serve HTML interface
- `GET /api/status` - JSON game state (state, matches, clientConnected, mode)
- `POST /api/reset` - Reset game to initial state
- `POST /api/mode?mode=0|1` - Set game mode (0=Free, 1=Ordered)
- `POST /api/test` - Trigger test mode

**Hardware Testing:**
- Upload firmware to receptacle controller ESP32
- Connect to "PipePuzzle" WiFi network
- Access http://192.168.4.1 in browser
- Verify status updates and controls work

---

### TASK 7: Ordered Game Mode [MEDIUM PRIORITY]
**Status:** COMPLETED
**Milestone:** Second game mode with sequence matching

- [x] Add game mode enum (FREE_MATCH, ORDERED_MATCH)
- [x] Implement order tracking for ordered mode
- [x] Add "blink count" animation for receptacles (1x, 2x, 3x, 4x blinks)
- [x] Validate sequence in ordered mode
- [x] Trigger glitch animation for wrong sequence
- [x] Integrate with web interface for mode switching

**Validation:** Both projects compile successfully with ordered mode ✓

**Files Modified:**
- `hose_controller/include/animation.h` - Added BLINK state to HoseAnimationState enum
- `hose_controller/src/animation.cpp` - Implemented updateBlink() with blink count support:
  - Blinks N times where N is the sequence position (1-4)
  - 150ms on/off interval
  - Pause between blink cycles for clear visual indication
- `hose_controller/include/wifi_client.h` - Added BlinkCountCallback for BLINK message handling
- `hose_controller/src/wifi_client.cpp` - Added BLINK message parsing and callback
- `hose_controller/include/wifi_config.h` - Added MSG_BLINK command and STATE_BLINK constant
- `hose_controller/src/main.cpp` - Added onBlinkCount callback and setHoseBlinkCount function

- `receptacle_controller/include/animation.h` - Added BLINK state to ReceptacleAnimationState enum
- `receptacle_controller/src/animation.cpp` - Implemented updateBlink() for receptacles
- `receptacle_controller/include/game_logic.h` - Added:
  - GameModeLogic enum (UNORDERED, ORDERED)
  - _nextExpectedIndex for sequence tracking
  - OrderSequenceCallback type
  - setGameMode(), getGameMode(), getNextExpectedIndex() methods
- `receptacle_controller/src/game_logic.cpp` - Implemented ordered mode logic:
  - processDetection() validates both correct hose AND correct order in ordered mode
  - Advances _nextExpectedIndex on correct match
  - Triggers OrderSequenceCallback on sequence position change
- `receptacle_controller/include/wifi_server.h` - Added sendBlinkCount() method
- `receptacle_controller/src/wifi_server.cpp` - Implemented sendBlinkCount()
- `receptacle_controller/include/wifi_config.h` - Added MSG_BLINK and STATE_BLINK
- `receptacle_controller/src/main.cpp` - Integrated ordered mode:
  - setBlinkState() function sets BLINK animation on both controllers
  - setupOrderedModeBlinkIndicators() initializes all receptacles with blink counts
  - onOrderSequenceChange() callback updates blink indicators on progression
  - Web interface mode change syncs with GameLogic mode

**Ordered Mode Behavior:**
1. When ordered mode is activated via web interface:
   - All receptacles enter BLINK state
   - Receptacle 0 blinks 1x, receptacle 1 blinks 2x, etc. to indicate sequence
   - Same blink pattern is sent to corresponding hoses via WiFi
2. Players must match receptacles in order (0 → 1 → 2 → 3)
3. Correct match in order → MATCHED animation, sequence advances
4. Wrong match OR out-of-order → GLITCH animation
5. All 4 correct in order → WIN celebration

**Requirements from spec:** ✓
- Receptacles blink once, twice, thrice, etc. to indicate order ✓
- Wrong order triggers glitch animation ✓
- Must match both correct receptacle AND correct order ✓

**Hardware Testing:**
- Upload firmware to both ESP32 controllers
- Connect to "PipePuzzle" WiFi and access http://192.168.4.1
- Select "Ordered Match" from game mode dropdown
- Observe receptacles blinking to indicate sequence (1x, 2x, 3x, 4x)
- Test matching in correct order (should show MATCHED animations)
- Test matching out of order (should show GLITCH animation)
- Complete all 4 in order to trigger celebration
````

## Important Guidelines

1. **Be Autonomous**:
   - Make decisions without asking
   - Use codebase patterns as guidance
   - If something is unclear, make a reasonable decision and note the assumption

2. **Be Thorough**:
   - Read all context files COMPLETELY before planning
   - Research actual code patterns using parallel sub-tasks
   - Include specific file paths and line numbers
   - Write measurable success criteria with clear automated vs manual distinction

3. **Be Practical**:
   - Focus on incremental, testable changes
   - Consider migration and rollback
   - Think about edge cases
   - Include "what we're NOT doing"

4. **Organize Around Verifiable Milestones**:
   - Each TASK should have a clear, verifiable milestone
   - The milestone describes what completing the task achieves
   - Include validation steps that can confirm the milestone is met
   - Link requirements back to the original spec/issue

5. **Be Detailed About Files**:
   - Separate "Files to Create" from "Files to Modify"
   - For each file, describe what it contains or what changes are needed
   - Include implementation details like class names, methods, endpoints
   - This serves as a reference during implementation

6. **Use Collapsible Sections Sparingly**:
   - Use `<details>` tags to collapse the research section when writing the plan
   - Tasks themselves should be visible (not collapsed) for easy scanning
   - Always include blank line after `<summary>` and before `</details>` for GitHub markdown rendering

7. **Track Progress**:
   - Use TodoWrite to track planning tasks
   - Update todos as you complete research

8. **No Open Questions in Final Plan**:
   - If you encounter open questions during planning, research more
   - Do NOT write the plan with unresolved questions
   - The implementation plan must be complete and actionable
   - Every decision must be made before finalizing the plan
   - Note assumptions where you made autonomous decisions

## Priority Levels

Use these priority levels for tasks:
- **[HIGH PRIORITY]** - Core functionality, blocking other tasks
- **[MEDIUM PRIORITY]** - Important but not blocking
- **[LOW PRIORITY]** - Nice to have, can be deferred

## Common Patterns

### For Database Changes:
- Start with schema/migration
- Add store methods
- Update business logic
- Expose via API

### For New Features:
- Research existing patterns first
- Start with data model
- Build backend logic
- Add API endpoints
- Implement UI last

### For Refactoring:
- Document current behavior
- Plan incremental changes
- Maintain backwards compatibility
- Include migration strategy

## Sub-task Spawning Best Practices

When spawning research sub-tasks:

1. **Spawn multiple tasks in parallel** for efficiency
2. **Each task should be focused** on a specific area
3. **Be specific about what to search for**
4. **Request specific file:line references** in responses
5. **Wait for all tasks to complete** before synthesizing
6. **Verify sub-task results**:
   - If a sub-task returns unexpected results, spawn follow-up tasks
   - Cross-check findings against the actual codebase

## Output

When done, output a brief summary:
```
Done - Plan posted to issue #X.
```
