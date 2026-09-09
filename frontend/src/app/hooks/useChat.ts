"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  type Message,
  type Assistant,
  type Checkpoint,
} from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import type { UseStreamThread } from "@langchain/langgraph-sdk/react";
import type { TodoItem } from "@/app/types/types";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";

import type { MemoryOperation } from "@/app/types/memory";

type FileData = {
  content: string;
  encoding: "utf-8" | "base64";
  created_at: string;
  modified_at: string;
};

export type RecalledMemory = {
  id: string;
  kind: string;
  origin: string;
  version_id: string;
  status: string;
  text: string;
  recorded_at: string;
  reason: string;
  sources: { id: string; role: string; excerpt: string }[];
};

export type StateType = {
  messages: Message[];
  todos: TodoItem[];
  files: Record<string, FileData | string>;
  recalled_memories?: RecalledMemory[];
  memory_changes?: string[];
  memory_status?: string;
  memory_interaction_id?: string | null;
  memory_operations?: MemoryOperation[];
  project_id?: string;
  demo_mode?: boolean;
  email?: {
    id?: string;
    subject?: string;
    page_content?: string;
  };
  ui?: any;
};

export function useChat({
  activeAssistant,
  onHistoryRevalidate,
  thread,
}: {
  activeAssistant: Assistant | null;
  onHistoryRevalidate?: () => void;
  thread?: UseStreamThread<StateType>;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const client = useClient();
  const [memoryStatus, setMemoryStatus] = useState("ready");

  const stream = useStream<StateType>({
    assistantId: activeAssistant?.assistant_id || "",
    client: client ?? undefined,
    reconnectOnMount: true,
    threadId: threadId ?? null,
    onThreadId: setThreadId,
    defaultHeaders: { "x-auth-scheme": "langsmith" },
    // Enable fetching state history when switching to existing threads
    fetchStateHistory: true,
    // Revalidate thread list when stream finishes, errors, or creates new thread
    onFinish: (state) => {
      setMemoryStatus(state.values.memory_status ?? "ready");
      onHistoryRevalidate?.();
    },
    onError: (error) => {
      setMemoryStatus("error");
      toast.error(error instanceof Error ? error.message : String(error));
      onHistoryRevalidate?.();
    },
    onCustomEvent: (event) => {
      if (event && typeof event === "object" && "memory_status" in event) {
        setMemoryStatus(String(event.memory_status));
      }
    },
    onCreated: onHistoryRevalidate,
    thread,
  });

  useEffect(() => {
    setMemoryStatus(stream.values.memory_status ?? "ready");
  }, [threadId, stream.values.memory_status]);

  const sendMessage = useCallback(
    (content: string) => {
      setMemoryStatus("ready");
      const newMessage: Message = { id: uuidv4(), type: "human", content };
      stream.submit(
        { messages: [newMessage] },
        {
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), newMessage],
          }),
          config: { ...(activeAssistant?.config ?? {}), recursion_limit: 100 },
        }
      );
      // Update thread list immediately when sending a message
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const runSingleStep = useCallback(
    (
      messages: Message[],
      checkpoint?: Checkpoint,
      isRerunningSubagent?: boolean,
      optimisticMessages?: Message[]
    ) => {
      if (checkpoint) {
        stream.submit(undefined, {
          ...(optimisticMessages
            ? { optimisticValues: { messages: optimisticMessages } }
            : {}),
          config: activeAssistant?.config,
          checkpoint: checkpoint,
          ...(isRerunningSubagent
            ? { interruptAfter: ["tools"] }
            : { interruptBefore: ["tools"] }),
        });
      } else {
        stream.submit(
          { messages },
          { config: activeAssistant?.config, interruptBefore: ["tools"] }
        );
      }
    },
    [stream, activeAssistant?.config]
  );

  const setFiles = useCallback(
    async (files: Record<string, string>) => {
      if (!threadId) return;
      // TODO: missing a way how to revalidate the internal state
      // I think we do want to have the ability to externally manage the state
      const now = new Date().toISOString();
      const values = Object.fromEntries(
        Object.entries(files).map(([path, text]) => {
          const previous = stream.values.files?.[path];
          return [
            path,
            {
              content: text,
              encoding: "utf-8",
              created_at:
                typeof previous === "object" ? previous.created_at : now,
              modified_at: now,
            },
          ];
        })
      );
      await client.threads.updateState(threadId, { values: { files: values } });
    },
    [client, threadId, stream.values.files]
  );

  const continueStream = useCallback(
    (hasTaskToolCall?: boolean) => {
      stream.submit(undefined, {
        config: {
          ...(activeAssistant?.config || {}),
          recursion_limit: 100,
        },
        ...(hasTaskToolCall
          ? { interruptAfter: ["tools"] }
          : { interruptBefore: ["tools"] }),
      });
      // Update thread list when continuing stream
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const markCurrentThreadAsResolved = useCallback(() => {
    stream.submit(null, { command: { goto: "__end__", update: null } });
    // Update thread list when marking thread as resolved
    onHistoryRevalidate?.();
  }, [stream, onHistoryRevalidate]);

  const resumeInterrupt = useCallback(
    (value: any) => {
      stream.submit(null, { command: { resume: value } });
      // Update thread list when resuming from interrupt
      onHistoryRevalidate?.();
    },
    [stream, onHistoryRevalidate]
  );

  const stopStream = useCallback(() => {
    stream.stop();
  }, [stream]);

  const files = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(stream.values.files ?? {}).map(([path, file]) => [
          path,
          typeof file === "string" ? file : file.content,
        ])
      ),
    [stream.values.files]
  );

  return {
    stream,
    threadId,
    memoryInteractionId: stream.values.memory_interaction_id,
    memoryOperations: stream.values.memory_operations ?? [],
    todos: stream.values.todos ?? [],
    files,
    recalledMemories: stream.values.recalled_memories ?? [],
    memoryChanges: stream.values.memory_changes ?? [],
    memoryStatus,
    projectId: stream.values.project_id,
    demoMode: stream.values.demo_mode ?? false,
    email: stream.values.email,
    ui: stream.values.ui,
    setFiles,
    messages: stream.messages,
    isLoading: stream.isLoading,
    isThreadLoading: stream.isThreadLoading,
    interrupt: stream.interrupt,
    getMessagesMetadata: stream.getMessagesMetadata,
    sendMessage,
    runSingleStep,
    continueStream,
    stopStream,
    markCurrentThreadAsResolved,
    resumeInterrupt,
  };
}
