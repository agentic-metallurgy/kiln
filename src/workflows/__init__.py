"""Workflow definitions for agentic-metallurgy.

This module provides workflow classes that define sequences of prompts
for Claude to execute when processing GitHub issues.

Available workflows:
- PrepareWorkflow: Clones or updates the main repo in the workspace
- ResearchWorkflow: Analyzes issues and explores the codebase
- PlanWorkflow: Creates detailed implementation plans
- ImplementWorkflow: Executes the implementation plan
- TestAccessWorkflow: Simple test to verify GitHub access works
"""

from src.workflows.base import Workflow, WorkflowContext
from src.workflows.implement import ImplementWorkflow
from src.workflows.plan import PlanWorkflow
from src.workflows.prepare import PrepareWorkflow
from src.workflows.prepare_implementation import PrepareImplementationWorkflow
from src.workflows.process_comments import ProcessCommentsWorkflow
from src.workflows.research import ResearchWorkflow
from src.workflows.test_access import TestAccessWorkflow

__all__ = [
    "Workflow",
    "WorkflowContext",
    "PrepareWorkflow",
    "PrepareImplementationWorkflow",
    "ResearchWorkflow",
    "PlanWorkflow",
    "ImplementWorkflow",
    "ProcessCommentsWorkflow",
    "TestAccessWorkflow",
]
