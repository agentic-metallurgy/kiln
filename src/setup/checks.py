"""Pre-flight checks for required CLI tools."""

import subprocess


class SetupError(Exception):
    """Raised when setup validation fails."""

    pass


def check_required_tools() -> None:
    """Check that required CLI tools are available.

    Checks for:
    - gh CLI (GitHub CLI)
    - claude CLI (Claude Code)

    Raises:
        SetupError: If any required tool is missing with installation instructions
    """
    errors = []

    # Check gh CLI
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        errors.append("gh CLI not found. Install from: https://cli.github.com/")
    except subprocess.CalledProcessError as e:
        errors.append(f"gh CLI error: {e.stderr.decode() if e.stderr else str(e)}")

    # Check claude CLI
    try:
        subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        errors.append(
            "claude CLI not found. Install from: "
            "https://docs.anthropic.com/en/docs/claude-code/overview"
        )
    except subprocess.CalledProcessError as e:
        errors.append(f"claude CLI error: {e.stderr.decode() if e.stderr else str(e)}")

    if errors:
        raise SetupError("\n".join(errors))
