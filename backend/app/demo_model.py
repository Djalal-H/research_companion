"""Credential-free scripted model for integration testing, never a live-model fallback.

It invokes the real Deep Agents planning/filesystem and application tools. It does
not assess research quality. Select explicitly with RESEARCH_MODEL=demo.
"""

import json
import re
import time
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class DemoModel(BaseChatModel):
    model_name: str = "demo:scripted"

    @property
    def _llm_type(self):
        return "demo"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        start = max(i for i, message in enumerate(messages) if isinstance(message, HumanMessage))
        observations = [m for m in messages[start:] if isinstance(m, ToolMessage)]
        names = [m.name for m in observations]
        tasks = [
            {"content": "Read the memory research papers", "status": "in_progress"},
            {"content": "Write a source-backed report", "status": "pending"},
        ]
        report_path = f"/reports/research-{messages[start].id}.md"
        if not names:
            name, args = "write_todos", {"todos": tasks}
        elif "search_papers" not in names:
            name, args = "search_papers", {"query": "A-Mem Mem0 memory"}
        elif names.count("read_paper") == 0:
            name, args = "read_paper", {"paper_id": "amem"}
        elif names.count("read_paper") == 1:
            name, args = "read_paper", {"paper_id": "mem0"}
        elif "write_file" not in names:
            system_text = messages[0].text
            match = re.search(r"<project_memory>(.*?)</project_memory>", system_text, re.S)
            recalled = json.loads(match.group(1)) if match else []
            lines = [
                "# Research companion scripted report",
                "",
                "Scripted demo: this validates the integration, not research reasoning.",
                "",
                "## Recalled project evidence",
                "",
            ]
            for note in recalled:
                lines.append(
                    f"- {note['text']} [memory:{note['id']}; source:{note['sources'][0]['id']}]"
                )
            if not recalled:
                lines.append("No matching project memories were retrieved.")
            lines.extend(["", "## Papers read", ""])
            for observation in observations:
                if observation.name == "read_paper":
                    paper = json.loads(observation.content)
                    section = paper["sections"][0]
                    lines.append(f"- [{paper['title']}]({section['url']}) [{section['source_id']}]")
            if messages[start].text.lower().startswith("design "):
                lines.extend(
                    [
                        "",
                        "## Proposed smallest experiment",
                        "",
                        "Scripted proposal, not an accepted user decision or measured result.",
                        "Use the current objective and time constraint cited above "
                        "to scope the work.",
                    ]
                )
                if any(
                    any(term in n["text"].lower() for term in ("one week", "a week"))
                    for n in recalled
                ):
                    lines.append(
                        "One-week schedule: day 1 prepare cases; days 2–3 run changes; "
                        "days 4–5 inspect current and historical recall; "
                        "days 6–7 review source accuracy and document failures."
                    )
                if any("changing facts" in n["text"].lower() for n in recalled):
                    lines.append(
                        "Focus on changing facts: use a small set of initial facts, "
                        "explicit changes, repeated facts, and corrections. "
                        "Ask current-state and historical questions in fresh threads. "
                        "Record stale-fact errors and whether citations support each answer."
                    )
                lines.append(
                    "Use the observed Mem0 reconciliation method and A-MEM note "
                    "organization as design references; this is not a reproduction "
                    "or a claim of comparative performance."
                )
            lines.extend(["", "Use a live model for a reasoned comparison or experiment plan."])
            name, args = "write_file", {"file_path": report_path, "content": "\n".join(lines)}
        elif names.count("write_todos") == 1:
            name, args = (
                "write_todos",
                {"todos": [{**task, "status": "completed"} for task in tasks]},
            )
        else:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="Scripted demo complete. Read two papers and saved "
                            f"`{report_path}`. The report includes any recalled project evidence "
                            "and their source references."
                        )
                    )
                ]
            )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="", tool_calls=[{"id": str(uuid4()), "name": name, "args": args}]
                    )
                )
            ]
        )

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._generate(messages).generations[0].message
        if message.tool_calls:
            call = message.tool_calls[0]
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "id": call["id"],
                            "name": call["name"],
                            "args": json.dumps(call["args"]),
                            "index": 0,
                        }
                    ],
                )
            )
        else:
            for offset in range(0, len(message.content), 40):
                time.sleep(0.02)
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=message.content[offset : offset + 40])
                )
