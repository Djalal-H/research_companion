# Research Companion UI

Adapted from the official Deep Agents UI. See [UPSTREAM.md](UPSTREAM.md) for the
pinned revision, license, and local changes. Full setup and phase-one limitations
are documented in the [project README](../README.md).

```sh
npm ci
npm run dev
```

The frontend defaults to the local LangGraph server at `http://127.0.0.1:2024`,
with assistant ID `research`. Start the backend before sending a message.

Validation: `npm run typecheck`, `npm run lint`, and `npm run build -- --webpack`.
The browser smoke test was skipped at the user's request.
