"use client";

import { useEffect, useState } from "react";
import { useChatContext } from "@/providers/ChatProvider";
import { useMemoryClient } from "@/providers/ClientProvider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  Evidence,
  InteractionDetail,
  MemoryOperation,
  NoteDetail,
} from "@/app/types/memory";

function EvidenceList({ sources }: { sources: Evidence[] }) {
  return (
    <div className="space-y-2 rounded-lg border border-border bg-muted/20 p-3">
      {sources.map((source) => (
        <details
          key={source.id}
          className="rounded-md border border-border/70 bg-background px-3 py-2"
        >
          <summary className="cursor-pointer break-all font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            source:{source.id} · {source.role}
          </summary>
          <p className="text-xs text-muted-foreground">
            {source.recorded_at} · thread:{source.thread_id}
          </p>
          {source.source_location && (
            <p className="break-all text-xs">{source.source_location}</p>
          )}
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-xs leading-5">
            {source.content}
          </pre>
        </details>
      ))}
    </div>
  );
}

function Operations({
  operations,
  select,
}: {
  operations: MemoryOperation[];
  select: (id: string) => void;
}) {
  return (
    <ul className="space-y-2">
      {operations.map((op) => (
        <li
          key={op.id}
          className="rounded-lg border border-border bg-background p-3"
        >
          <p className="font-medium">
            {op.action ?? "Consolidation failure"} · {op.status}
          </p>
          <p>{op.reason}</p>
          <p className="text-xs text-muted-foreground">{op.recorded_at}</p>
          <div className="flex flex-wrap gap-2">
            {op.target_note_ids.map((id) => (
              <button
                key={id}
                className="break-all text-left font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => select(id)}
              >
                Inspect {id}
              </button>
            ))}
          </div>
          <p className="break-all text-xs">
            Evidence: {op.input_event_ids.join(", ") || "None"}
          </p>
        </li>
      ))}
    </ul>
  );
}

function Inspector({
  note,
  versionId,
  select,
}: {
  note: NoteDetail;
  versionId?: string;
  select: (id: string) => void;
}) {
  return (
    <section
      aria-label="Selected memory details"
      className="space-y-3 rounded-xl border border-border bg-card p-4 shadow-sm"
    >
      <p className="break-all font-medium">
        memory:{note.id} · {note.kind} · {note.origin}
      </p>
      <p>{note.subject}</p>
      {note.versions.map((version) => (
        <details
          key={version.version_id}
          open={version.version_id === (versionId ?? note.current_version_id)}
        >
          <summary className="cursor-pointer break-all font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {version.status} · version:{version.version_id}
            {version.version_id === versionId ? " · recalled version" : ""}
          </summary>
          <p className="whitespace-pre-wrap">{version.text}</p>
          <p className="text-xs text-muted-foreground">
            Recorded {version.recorded_at}
            {version.event_time ? ` · Event ${version.event_time}` : ""}
          </p>
          {version.metadata && (
            <p className="mt-2">
              Context: {version.metadata.context}
              <br />
              Tags: {version.metadata.tags.join(", ")} · Keywords:{" "}
              {version.metadata.keywords.join(", ")}
            </p>
          )}
          <EvidenceList sources={version.sources} />
          <details className="mt-3 rounded-md border border-border/70 p-2">
            <summary className="cursor-pointer font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Metadata history ({version.metadata_history.length})
            </summary>
            {version.metadata_history.map((revision) => (
              <div
                key={revision.id}
                className="my-2 rounded-md border border-border bg-muted/20 p-3"
              >
                <p>
                  {revision.reason} · {revision.recorded_at}
                </p>
                <p>{revision.metadata.context}</p>
                <p>
                  Tags: {revision.metadata.tags.join(", ")} · Keywords:{" "}
                  {revision.metadata.keywords.join(", ")}
                </p>
                <p className="break-all text-xs">
                  Evidence: {revision.source_ids.join(", ")}
                </p>
              </div>
            ))}
          </details>
        </details>
      ))}
      <details className="rounded-md border border-border/70 p-2">
        <summary className="cursor-pointer font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Operation history ({note.operations.length})
        </summary>
        <Operations
          operations={note.operations}
          select={select}
        />
      </details>
      <details className="rounded-md border border-border/70 p-2">
        <summary className="cursor-pointer font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          All supporting evidence
        </summary>
        <EvidenceList sources={note.evidence} />
      </details>
    </section>
  );
}

export function MemorySummary() {
  const { threadId } = useChatContext();
  return <MemoryPanel key={threadId ?? "new"} />;
}

function MemoryPanel() {
  const {
    recalledMemories,
    memoryChanges,
    memoryStatus,
    projectId,
    demoMode,
    memoryInteractionId,
    memoryOperations,
    isLoading,
  } = useChatContext();
  const readMemory = useMemoryClient();
  const [tab, setTab] = useState("recalled");
  const [selection, setSelection] = useState<{
    id: string;
    versionId?: string;
  } | null>(null);
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [interaction, setInteraction] = useState<InteractionDetail | null>(
    null
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [history, setHistory] = useState(false);
  const select = (id: string, versionId?: string) => {
    setNote(null);
    setSelection({ id, versionId });
  };

  useEffect(() => {
    const controller = new AbortController();
    setNote(null);
    setInteraction(null);
    setError("");
    const requests: Promise<void>[] = [];
    if (selection)
      requests.push(
        readMemory<NoteDetail>(
          `notes/${encodeURIComponent(selection.id)}`,
          controller.signal
        ).then((value) => {
          if (!controller.signal.aborted) setNote(value);
        })
      );
    if (tab === "changes" && memoryInteractionId)
      requests.push(
        readMemory<InteractionDetail>(
          `interactions/${encodeURIComponent(memoryInteractionId)}`,
          controller.signal
        ).then((value) => {
          if (!controller.signal.aborted) setInteraction(value);
        })
      );
    setLoading(requests.length > 0);
    Promise.all(requests)
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error ? cause.message : "Could not load details."
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [
    selection,
    tab,
    memoryInteractionId,
    memoryStatus,
    isLoading,
    retry,
    readMemory,
  ]);

  const connections =
    note?.connections.filter((link) => history || link.status === "active") ??
    [];
  return (
    <aside
      aria-label="Project memory"
      className="border-b border-border bg-muted/20 px-4 py-3 text-sm sm:px-6"
    >
      <div className="mx-auto max-w-[1024px] space-y-2">
        <div
          aria-live="polite"
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
          role="status"
        >
          <span className="font-semibold tracking-tight">
            Project memory{projectId ? ` · ${projectId}` : ""}
          </span>
          <span
            className={
              memoryStatus === "updating"
                ? "font-medium text-[hsl(var(--ring))]"
                : "text-muted-foreground"
            }
          >
            {memoryStatus === "updating"
              ? "Updating memory…"
              : `${recalledMemories.length} recalled · ${memoryChanges.length} changed this turn`}
          </span>
          {demoMode && (
            <span className="border-primary/20 bg-primary/10 rounded-full border px-2 py-0.5 text-xs font-medium text-primary">
              Scripted demo · no live model
            </span>
          )}
        </div>
        {memoryStatus === "error" && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-destructive"
          >
            Memory was not updated. Your response remains available.
          </p>
        )}
        <Tabs
          value={tab}
          onValueChange={setTab}
        >
          <TabsList aria-label="Memory views">
            <TabsTrigger value="recalled">Recalled</TabsTrigger>
            <TabsTrigger value="changes">Changes</TabsTrigger>
            <TabsTrigger value="connections">Connections</TabsTrigger>
          </TabsList>
          <div className="max-h-[45vh] space-y-3 overflow-auto pr-1 sm:pr-2">
            <TabsContent
              value="recalled"
              className="space-y-2"
            >
              {!recalledMemories.length && (
                <p>No memories recalled for this request.</p>
              )}
              {recalledMemories.map((memory) => (
                <article
                  key={memory.version_id ?? memory.id}
                  className="rounded-xl border border-border bg-card p-3 shadow-sm"
                >
                  <p className="whitespace-pre-wrap">{memory.text}</p>
                  <p className="text-xs text-muted-foreground">
                    {memory.kind} · {memory.origin} · {memory.status} ·{" "}
                    {memory.reason}
                  </p>
                  {memory.sources.map((source) => (
                    <blockquote
                      key={source.id}
                      className="my-3 rounded-md bg-muted/30 px-3 py-2"
                    >
                      <p>{source.excerpt}</p>
                      <p className="break-all text-xs">
                        source:{source.id} · {source.role}
                      </p>
                    </blockquote>
                  ))}
                  <button
                    className="font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => select(memory.id, memory.version_id)}
                  >
                    Inspect evidence and history
                  </button>
                </article>
              ))}
            </TabsContent>
            <TabsContent
              value="changes"
              className="space-y-2"
            >
              <p className="text-muted-foreground">
                Latest interaction · fact operations, ENRICH (new metadata),
                EVOLVE (revised metadata), and LINK.
              </p>
              {!(interaction?.operations ?? memoryOperations).length && (
                <p>No recorded operations for this interaction.</p>
              )}
              <Operations
                operations={interaction?.operations ?? memoryOperations}
                select={select}
              />
              {interaction && (
                <details className="rounded-md border border-border/70 p-2">
                  <summary className="cursor-pointer font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    Interaction evidence · {interaction.status}
                  </summary>
                  <EvidenceList sources={interaction.evidence} />
                </details>
              )}
              {!memoryOperations.length &&
                memoryChanges.map((id) => (
                  <button
                    key={id}
                    className="block break-all underline"
                    onClick={() => select(id)}
                  >
                    Inspect changed memory {id}
                  </button>
                ))}
            </TabsContent>
            <TabsContent
              value="connections"
              className="space-y-2"
            >
              <p>
                Select a memory from Recalled or Changes to inspect its
                immediate connections.
              </p>
              <label className="flex gap-2">
                <input
                  type="checkbox"
                  checked={history}
                  onChange={(event) => setHistory(event.target.checked)}
                />
                Include historical connections
              </label>
              {note && !connections.length && (
                <p>
                  No {history ? "" : "current "}connections for this memory.
                </p>
              )}
              {connections.map((link) => (
                <article
                  key={link.id}
                  className="space-y-1 rounded-lg border border-border bg-card p-3 shadow-sm"
                >
                  <p>
                    {link.relation} · {link.status} ·{" "}
                    {link.from_note_id === note?.id ? "outgoing" : "incoming"}
                  </p>
                  <p>
                    {link.neighbor_text} · {link.neighbor_status}
                  </p>
                  <p>{link.reason}</p>
                  <p className="break-all text-xs">
                    {link.from_version} → {link.to_version}
                  </p>
                  <p className="break-all text-xs">
                    Evidence: {link.source_ids.join(", ")}
                  </p>
                  <button
                    className="font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() =>
                      select(link.neighbor_id, link.neighbor_version_id)
                    }
                  >
                    Inspect connected version
                  </button>
                </article>
              ))}
            </TabsContent>
            {(selection || (tab === "changes" && memoryInteractionId)) && (
              <button
                className="font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                disabled={loading}
                onClick={() => setRetry((value) => value + 1)}
              >
                Refresh details
              </button>
            )}
            {loading && <p role="status">Loading memory details…</p>}
            {error && (
              <p role="alert">
                {error}{" "}
                <button
                  className="font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => setRetry((value) => value + 1)}
                >
                  Retry
                </button>
              </p>
            )}
            {note && (
              <Inspector
                note={note}
                versionId={selection?.versionId}
                select={select}
              />
            )}
          </div>
        </Tabs>
      </div>
    </aside>
  );
}
