from typing import NotRequired

from deepagents.graph import DeepAgentState


class ResearchState(DeepAgentState):
    # Deep Agents composes standard files and todos channels from its middleware.
    recalled_memories: NotRequired[list[dict]]
    memory_changes: NotRequired[list[str]]
    memory_interaction_id: NotRequired[str | None]
    memory_operations: NotRequired[list[dict]]
    memory_status: NotRequired[str]
    project_id: NotRequired[str]
    demo_mode: NotRequired[bool]
