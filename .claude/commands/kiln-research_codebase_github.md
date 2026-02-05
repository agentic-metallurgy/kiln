# Research Codebase

You are tasked with conducting comprehensive research across the codebase to answer user questions by spawning parallel sub-agents and synthesizing their findings.

You are running in **headless, non-interactive mode** as part of an automated workflow. You MUST complete the entire process autonomously without asking questions or waiting for user input.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT Ask clarifying questions
- Do NOT Wait for user approval
- Do NOT Present options for the user to choose from
- Do NOT Request feedback before proceeding

**CRITICAL: DO NOT IMPLEMENT. DO NOT WRITE CODE. DO NOT USE WRITE/EDIT TOOLS. DO NOT MODIFY ANY SOURCE FILES.**

**IT IS NOT YOUR JOB.** There are others who are tasked with those steps.

**Your role is research ONLY.** You may:
- Read files
- Search code
- Spawn sub-agents for analysis
- Post findings to the GitHub issue (via `gh issue edit`)

You MUST NOT:
- Write or edit any source files
- Modify any code
- Create new files
- Use Write, Edit, or NotebookEdit tools
- Make git commits or push changes

This command is always invoked with a GitHub/GHE issue reference (format: `hostname/owner/repo`):

$ARGUMENTS

   1. Read the GitHub issue using `gh`:
      ```bash
      GH_HOST=<hostname> gh issue view https://<hostname>/<owner>/<repo>/issues/<num>
      ```
   2. Understand the requirements and/or problem statement and/or constraints as much as they are provided.
   3. **Read all mentioned files immediately and FULLY**:
     - Issue description references
     - Research documents linked
     - Any JSON/data files mentioned
   
   - **IMPORTANT**: Use the Read tool WITHOUT limit/offset parameters to read entire files
   - **CRITICAL**: Read these files yourself in the main context before spawning any sub-tasks
   - This ensures you have full context before decomposing the research

2. **Analyze and decompose the research question:**
   - Break down the user's query into composable research areas
   - Take time to ultrathink about the underlying patterns, connections, and architectural implications the user might be seeking
   - Identify specific components, patterns, or concepts to investigate
   - Create a research plan using TodoWrite to track all subtasks
   - Consider which directories, files, or architectural patterns are relevant

3. **Spawn parallel sub-agent tasks for comprehensive research:**
   - Create multiple Task agents to research different aspects concurrently

   The key is to use these agents intelligently:
   - Start with locator agents to find what exists
   - Then use analyzer agents on the most promising findings
   - Run multiple agents in parallel when they're searching for different things
   - Each agent knows its job - just tell it what you're looking for
   - Don't write detailed prompts about HOW to search - the agents already know

4. **Wait for all sub-agents to complete and synthesize findings:**
   - IMPORTANT: Wait for ALL sub-agent tasks to complete before proceeding
   - Compile all sub-agent results (both codebase and thoughts findings)
   - Prioritize live codebase findings as primary source of truth
   - Connect findings across different components
   - Include specific file paths and line numbers for reference
   - Verify all thoughts/ paths are correct (e.g., thoughts/allison/ not thoughts/shared/ for personal files)
   - Highlight patterns, connections, and architectural decisions
   - Answer the user's specific questions with concrete evidence

5. **Post research to issue description (if GitHub issue specified):**
   - If a GitHub issue was specified, edit the issue DESCRIPTION to append a research section
   - The section MUST be wrapped in `<!-- kiln:research -->` and `<!-- /kiln:research -->` markers
   - Use `gh` to edit (NOT REST API, NOT curl):
     ```bash
     GH_HOST=<hostname> gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."
     ```
   - Preserve the original issue description content above the research section
   - Add a `---` separator before the research section
   - Use this structure for the appended section:

     ```markdown
     ---
     <!-- kiln:research -->
     ## Research Findings

     ### Summary
     [High-level findings answering the question]

     ### Key Discoveries
     - [Important finding with file:line reference]
     - [Pattern or convention discovered]
     - [Constraint or consideration]

     ### Detailed Findings

     #### [Component/Area 1]
     - Finding with reference (`file.ext:line`)
     - Connection to other components
     - Implementation details

     #### [Component/Area 2]
     ...

     ### Files Requiring Changes
     | File | Lines | Change |
     |------|-------|--------|
     | `path/to/file.py` | 123-145 | Description of change |

     ### Open Questions
     [Any areas that need further investigation]
     <!-- /kiln:research -->
     ```

6. **Sync and present findings:**
   - Present a concise summary of findings to the user
   - Include key file references for easy navigation
   - Ask if they have follow-up questions or need clarification

7. **Handle follow-up questions:**
   - If the user has follow-up questions, edit the research section in the issue description
   - Add new findings to the existing research section
   - Spawn new sub-agents as needed for additional investigation

## Important notes:
- Always use parallel Task agents to maximize efficiency and minimize context usage
- Always run fresh codebase research - never rely solely on existing research documents
- Focus on finding concrete file paths and line numbers for developer reference
- Research documents should be self-contained with all necessary context
- Each sub-agent prompt should be specific and focused on read-only operations
- Consider cross-component connections and architectural patterns
- Include temporal context (when the research was conducted)
- Link to GitHub when possible for permanent references
- Keep the main agent focused on synthesis, not deep file reading
- Encourage sub-agents to find examples and usage patterns, not just definitions
- **File reading**: Always read mentioned files FULLY (no limit/offset) before spawning sub-tasks
- **Critical ordering**: Follow the numbered steps exactly
  - ALWAYS read mentioned files first before spawning sub-tasks
  - ALWAYS wait for all sub-agents to complete before synthesizing
  - ALWAYS gather metadata before writing the document
  - NEVER write the research document with placeholder values
  - Preserve the exact directory structure
  - This ensures paths are correct for editing and navigation
- **Frontmatter consistency**:
  - Update frontmatter when adding follow-up research
  - Use snake_case for multi-word field names (e.g., `last_updated`, `git_commit`)
  - Tags should be relevant to the research topic and components studied
