# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary audience is potential researchers evaluating this portfolio project. They need to understand and experience how an agent can support research work while retaining useful context across interactions.

## Product Purpose

Research Companion is a local research assistant interface that lets people converse with an agent, work across persistent threads, and inspect project memory recalled or changed during a turn. Its portfolio purpose is to demonstrate agentic research and persistent memory through a working product experience.

## Positioning

The project demonstrates the connection between agentic research workflows and inspectable, persistent project memory in one interface. The memory layer is surfaced as part of the working conversation rather than being hidden as an implementation detail.

## Operating Context

The interface is evaluated in a browser and connects by default to a local LangGraph server at `http://127.0.0.1:2024` using the `research` assistant. A backend must be running before messages can be sent. Reviewers can start new conversations, revisit thread history, inspect tasks and files, and review recalled memory, memory changes, connections, supporting evidence, and operation history.

## Capabilities and Constraints

- Next.js web application with a React client UI.
- LangGraph/LangChain SDK integration for assistant discovery, streamed chat, threads, tool calls, and interrupt/resume flows.
- Configurable deployment URL, assistant ID, and optional LangSmith API key; local defaults are supported.
- Persistent thread history with status filtering and attention indicators.
- Project-memory status, recall, change tracking, evidence inspection, version history, and memory-operation details.
- Task and file views are available alongside chat.
- A credential-free scripted demo mode exists in the broader project workflow.
- The complete memory inspector and comparison-mode controls remain future milestones.
- Future work must preserve the product’s local/deployable LangGraph connection model and avoid fabricating research evidence, testimonials, benchmarks, or customer claims.

## Brand Commitments

- Product name: Research Companion.
- Existing metadata describes it as “A local research assistant with persistent project memory.”

## Evidence on Hand

- `README.md`: product name, local setup, backend endpoint, assistant default, and validation commands.
- `UPSTREAM.md`: provenance, pinned upstream revision, license context, local adaptations, and known milestone limitations.
- `src/app/page.tsx`: primary application shell, configuration flow, thread history, assistant selection, and conversation controls.
- `src/app/components/ChatInterface.tsx`: streamed chat, tasks, files, tool calls, interrupts, and message composition.
- `src/app/components/MemorySummary.tsx`: recalled memories, changes, connections, evidence, versions, and operation history.
- `src/app/hooks/useChat.ts` and `src/providers/ClientProvider.tsx`: chat and memory integration behavior.
- No external testimonials, customer studies, performance benchmarks, or other third-party proof are established; future work must not invent them.

## Product Principles

- Make agentic research tangible through a usable, working conversation.
- Keep persistent memory visible and inspectable.
- Preserve evidence and provenance around remembered information.
- Make the portfolio artifact understandable to a research-oriented evaluator.
- Support both a local demonstration and a configurable LangGraph deployment.
