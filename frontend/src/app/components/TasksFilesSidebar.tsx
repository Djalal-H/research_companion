"use client";

import React, {
  useMemo,
  useCallback,
  useState,
  useEffect,
  useRef,
} from "react";
import {
  FileText,
  CheckCircle,
  Circle,
  Clock,
  ChevronDown,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { TodoItem, FileItem } from "@/app/types/types";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { FileViewDialog } from "@/app/components/FileViewDialog";

export function FilesPopover({
  files,
  setFiles,
  editDisabled,
}: {
  files: Record<string, string>;
  setFiles: (files: Record<string, string>) => Promise<void>;
  editDisabled: boolean;
}) {
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);

  const handleSaveFile = useCallback(
    async (fileName: string, content: string) => {
      await setFiles({ ...files, [fileName]: content });
      setSelectedFile({ path: fileName, content: content });
    },
    [files, setFiles]
  );

  return (
    <>
      {Object.keys(files).length === 0 ? (
        <div className="flex h-full items-center justify-center p-4 text-center">
          <p className="text-xs text-muted-foreground">No files created yet</p>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-2">
          {Object.keys(files).map((file) => {
            const filePath = String(file);
            const rawContent = files[file];
            let fileContent: string;
            if (
              typeof rawContent === "object" &&
              rawContent !== null &&
              "content" in rawContent
            ) {
              const contentArray = (rawContent as { content: unknown }).content;
              if (Array.isArray(contentArray)) {
                fileContent = contentArray.join("\n");
              } else {
                fileContent = String(contentArray || "");
              }
            } else {
              fileContent = String(rawContent || "");
            }

            return (
              <button
                key={filePath}
                type="button"
                onClick={() =>
                  setSelectedFile({ path: filePath, content: fileContent })
                }
                className="hover:border-primary/40 group cursor-pointer space-y-1 truncate rounded-lg border border-border bg-background px-2 py-3 shadow-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                aria-label={`Open file ${filePath}`}
              >
                <FileText
                  size={24}
                  className="mx-auto text-muted-foreground transition-colors group-hover:text-primary"
                />
                <span className="mx-auto block w-full truncate break-words text-center text-sm leading-5 text-foreground">
                  {filePath}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {selectedFile && (
        <FileViewDialog
          file={selectedFile}
          onSaveFile={handleSaveFile}
          onClose={() => setSelectedFile(null)}
          editDisabled={editDisabled}
        />
      )}
    </>
  );
}

export const TasksFilesSidebar = React.memo<{
  todos: TodoItem[];
  files: Record<string, string>;
  setFiles: (files: Record<string, string>) => Promise<void>;
}>(({ todos, files, setFiles }) => {
  const { isLoading, interrupt } = useChatContext();
  const [tasksOpen, setTasksOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);

  // Track previous counts to detect when content goes from empty to having items
  const prevTodosCount = useRef(todos.length);
  const prevFilesCount = useRef(Object.keys(files).length);

  // Auto-expand when todos go from empty to having content
  useEffect(() => {
    if (prevTodosCount.current === 0 && todos.length > 0) {
      setTasksOpen(true);
    }
    prevTodosCount.current = todos.length;
  }, [todos.length]);

  // Auto-expand when files go from empty to having content
  const filesCount = Object.keys(files).length;
  useEffect(() => {
    if (prevFilesCount.current === 0 && filesCount > 0) {
      setFilesOpen(true);
    }
    prevFilesCount.current = filesCount;
  }, [filesCount]);

  const getStatusIcon = useCallback((status: TodoItem["status"]) => {
    switch (status) {
      case "completed":
        return (
          <CheckCircle
            size={12}
            className="text-success/80"
          />
        );
      case "in_progress":
        return (
          <Clock
            size={12}
            className="text-warning/80"
          />
        );
      default:
        return (
          <Circle
            size={10}
            className="text-tertiary/70"
          />
        );
    }
  }, []);

  const groupedTodos = useMemo(() => {
    return {
      pending: todos.filter((t) => t.status === "pending"),
      in_progress: todos.filter((t) => t.status === "in_progress"),
      completed: todos.filter((t) => t.status === "completed"),
    };
  }, [todos]);

  const groupedLabels = {
    pending: "Pending",
    in_progress: "In Progress",
    completed: "Completed",
  };

  return (
    <div className="min-h-0 w-full flex-1">
      <div className="flex h-full w-full flex-col p-0">
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
          <div className="flex items-center justify-between px-3 pb-1.5 pt-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Agent tasks
            </span>
            <button
              type="button"
              onClick={() => setTasksOpen((v) => !v)}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-transform duration-200 hover:bg-muted",
                tasksOpen ? "rotate-180" : "rotate-0"
              )}
              aria-label="Toggle tasks panel"
              aria-expanded={tasksOpen}
              aria-controls="agent-tasks-panel"
            >
              <ChevronDown size={14} />
            </button>
          </div>
          {tasksOpen && (
            <div
              id="agent-tasks-panel"
              className="rounded-xl border border-border bg-muted/20 px-3 pb-2"
            >
              <ScrollArea className="h-full">
                {todos.length === 0 ? (
                  <div className="flex h-full items-center justify-center p-4 text-center">
                    <p className="text-xs text-muted-foreground">
                      No tasks created yet
                    </p>
                  </div>
                ) : (
                  <div className="ml-1 p-0.5">
                    {Object.entries(groupedTodos).map(([status, todos]) => (
                      <div
                        key={status}
                        className="mb-4"
                      >
                        <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          {groupedLabels[status as keyof typeof groupedLabels]}
                        </h3>
                        {todos.map((todo, index) => (
                          <div
                            key={`${status}_${todo.id}_${index}`}
                            className="mb-1.5 flex items-start gap-2 rounded-sm p-1 text-sm"
                          >
                            {getStatusIcon(todo.status)}
                            <span className="flex-1 break-words leading-relaxed text-inherit">
                              {todo.content}
                            </span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          )}

          <div className="flex items-center justify-between px-3 pb-1.5 pt-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              File system
            </span>
            <button
              type="button"
              onClick={() => setFilesOpen((v) => !v)}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-transform duration-200 hover:bg-muted",
                filesOpen ? "rotate-180" : "rotate-0"
              )}
              aria-label="Toggle files panel"
              aria-expanded={filesOpen}
              aria-controls="file-system-panel"
            >
              <ChevronDown size={14} />
            </button>
          </div>
          {filesOpen && (
            <div
              id="file-system-panel"
              className="rounded-xl border border-border bg-muted/20 p-3"
            >
              <FilesPopover
                files={files}
                setFiles={setFiles}
                editDisabled={isLoading === true || interrupt !== undefined}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

TasksFilesSidebar.displayName = "TasksFilesSidebar";
