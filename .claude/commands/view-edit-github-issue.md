# View and Edit GitHub Issue

Simple test command to verify GitHub access works.

When invoked with an issue URL (e.g., `https://git.example.com/owner/repo/issues/123`):

1. View the issue:
   ```bash
   gh issue view <issue_url>
   ```

2. Get the current body:
   ```bash
   gh issue view <issue_url> --json body --jq '.body'
   ```

3. Append "i can access this." to the description:
   ```bash
   gh issue edit <issue_url> --body "<current_body>

   ---
   i can access this."
   ```

4. Confirm the edit was successful by viewing again.

That's it. Just do it.
