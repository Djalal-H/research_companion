Adapted from https://github.com/langchain-ai/deep-agents-ui at commit
`f6a4f34565b42688be06498031fc9351c152614e`. Upstream's MIT license is retained in LICENSE.

Local adaptations: local research graph defaults, Research Companion title, compact
memory state display, streamed memory status/errors, typed Deep Agents FileData
conversion on display and edits. The SDK's old `experimental_thread` option is now
`thread`. Backend integration tests use a credential-free scripted model; the UI
browser smoke test was skipped at the user's request.
Google font fetching was removed so builds do not depend on a font service.

The upstream ESLint 10 helper conflicted with its ESLint 9 dependency; the helper
is pinned to 9.39.1. npm replaces Yarn; package-lock.json pins all resolved packages.
The complete Memory inspector and comparison-mode controls remain later milestones.
