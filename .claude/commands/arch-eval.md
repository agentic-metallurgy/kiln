---
model: opus
---

# Architecture Evaluation Generator

Generate a new architecture evaluation document for Kiln.

## Instructions

1. **Create a feature branch** for this evaluation:
   ```bash
   git checkout -b arch-eval-$(date +%Y-%m-%d)
   ```

2. **Gather current codebase metrics** by running:
   - `wc -l src/*.py src/workflows/*.py` for source line counts
   - `python -m pytest tests/ --collect-only -q 2>/dev/null | tail -1` for test count
   - `git log -1 --format='%h'` for current commit hash
   - `git log --oneline $(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~50)..HEAD | head -30` for recent changes
   - `gh pr list --state merged --limit 20 --json number,title` for recent merged PRs, use to find all PRs since last evaluation.

3. **Read the previous evaluation** from the symlink target:
   - `readlink docs/_arch-evaluation-latest.md` to find the previous file
   - Read that file to understand the baseline for comparison

4. **Identify changes since last evaluation** by:
   - Comparing PR numbers mentioned in previous eval vs recent merged PRs
   - Noting new files in `src/` that weren't in previous code organization
   - Checking for new dependencies in `pyproject.toml`
   - Looking for new labels in daemon.py REQUIRED_LABELS

5. **Create the new evaluation document** at `docs/arch-evaluation-YYYY-MM-DD.md` with today's date, covering these sections:

   ### Document Structure

   ```markdown
   ## Architecture Evaluation

   **Date**: YYYY-MM-DD
   **Commit**: <short-hash>

   ### Changes Since Last Evaluation (<previous-date>)

   Key improvements since the previous evaluation:

   | PR | Change | Impact |
   |----|--------|--------|
   | #NNN | Description | Impact on architecture |

   ---

   ### Efficiency
   | Aspect | Rating | Notes |
   - API calls, Polling overhead, Parallelism, Caching, Comment fetching, Observability

   ### Maintainability
   | Aspect | Rating | Notes |
   - Separation of concerns, Protocol-based design, Configuration, Error handling, Testing, Logging
   - Include **Code organization** tree with line counts

   ### Ease of Use / Customization
   | Aspect | Rating | Notes |
   - Setup, Configuration, Workflow customization, Model selection, Status customization, Claude customization, Label management, Workspace structure

   ### Best Practices
   | Practice | Implemented | Notes |
   - Idempotency, Graceful shutdown, Thread safety, Secret management, Retry logic, Schema migrations, Logging, Security, Duplicate prevention, UX
   - Note improvements since last evaluation and what's still missing

   ### Modern Patterns
   | Pattern | Used | Notes |
   - Dataclasses, Protocol, Type hints, f-strings, Pathlib, Context managers, Async, contextvars, OpenTelemetry

   ### Trade-offs Analysis
   | Decision | Benefit | Cost |
   - Polling vs Webhooks, Labels as state, Claude CLI vs API, Issue description, Synchronous design, OTEL vs custom metrics, Thread pool vs async

   ---

   ## Metrics Comparison

   | Metric | <prev-date> | <today> | Change |
   |--------|-------------|---------|--------|
   | Test count | N | M | +X% |
   | Total source lines | ~N | ~M | +X% |
   | Workflows | N | M | +/-N |
   | Dependencies | N | M | +/-N |
   | Required labels | N | M | +/-N |

   ---

   ## Conclusion

   **Overall Score: NN/100**

   ### Score Breakdown

   Itemize what's missing from a perfect 100 score:

   | Gap | Points | Notes |
   |-----|--------|-------|
   | Gap description | -N | Why points were deducted |
   | ... | ... | ... |

   Include:
   - Which gaps are inherent/unfixable vs addressable
   - Easiest wins to improve the score

   ### Strengths & Improvements

   - Key strengths (unchanged from baseline)
   - New strengths (since last evaluation)
   - Recommended improvements (updated - strike through completed items)
   ```

6. **Update the symlink** after creating the document:
   ```bash
   cd docs && ln -sf arch-evaluation-YYYY-MM-DD.md _arch-evaluation-latest.md
   ```

7. **Commit the changes**:
   ```bash
   git add docs/arch-evaluation-YYYY-MM-DD.md docs/_arch-evaluation-latest.md
   git commit -m "docs: Add architecture evaluation YYYY-MM-DD"
   ```

8. **Push and create a PR**:
   ```bash
   git push -u origin arch-eval-$(date +%Y-%m-%d)
   gh pr create --title "docs: Architecture evaluation YYYY-MM-DD" --body "## Summary
   - New architecture evaluation comparing current state to previous evaluation
   - Updates symlink to point to new evaluation

   ## Changes
   [List key changes noted in the evaluation]"
   ```

9. **Verify** the symlink points to the new file and PR was created:
   ```bash
   ls -la docs/_arch-evaluation-latest.md
   gh pr view --web
   ```

## Rating Guidelines

- **Excellent**: Best-in-class implementation, no improvements needed
- **Good**: Solid implementation, minor improvements possible
- **Moderate**: Acceptable but clear room for improvement
- **Partial**: Incomplete implementation
- **No**: Not implemented

## Important Notes

- Compare ratings to previous evaluation and explain any changes
- Update the "Recommended improvements" section - strike through completed items with ~~text~~
- Be objective - if something regressed, note it
- Include PR numbers for all changes mentioned
- The metrics comparison should show actual deltas, not estimates
