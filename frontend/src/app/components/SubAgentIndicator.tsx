"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { CheckCircle2, ChevronDown, ChevronUp, Circle } from "lucide-react";
import type { SubAgent } from "@/app/types/types";

interface SubAgentIndicatorProps {
  subAgent: SubAgent;
  onClick: () => void;
  isExpanded?: boolean;
}

export const SubAgentIndicator = React.memo<SubAgentIndicatorProps>(
  ({ subAgent, onClick, isExpanded = true }) => {
    const isComplete = subAgent.status === "completed";
    const isError = subAgent.status === "error";
    return (
      <div className="w-fit max-w-[70vw] overflow-hidden rounded-xl border border-border bg-muted/20 shadow-sm outline-none">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClick}
          className="flex w-full items-center justify-between gap-3 border-none px-3 py-2 text-left shadow-none outline-none transition-colors duration-200 hover:bg-muted/60"
          aria-expanded={isExpanded}
          aria-label={`${isExpanded ? "Collapse" : "Expand"} ${
            subAgent.subAgentName
          } details`}
        >
          <div className="flex w-full items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {isComplete ? (
                <CheckCircle2
                  className="size-4 text-emerald-600 dark:text-emerald-400"
                  aria-hidden="true"
                />
              ) : (
                <Circle
                  className={
                    isError
                      ? "size-3.5 fill-amber-500 text-amber-500"
                      : "size-3.5 fill-primary/30 text-primary"
                  }
                  aria-hidden="true"
                />
              )}
              <span className="font-sans text-sm font-semibold leading-5 tracking-tight text-foreground">
                {subAgent.subAgentName}
              </span>
            </div>
            {isExpanded ? (
              <ChevronUp
                size={14}
                className="shrink-0 text-muted-foreground"
              />
            ) : (
              <ChevronDown
                size={14}
                className="shrink-0 text-muted-foreground"
              />
            )}
          </div>
        </Button>
      </div>
    );
  }
);

SubAgentIndicator.displayName = "SubAgentIndicator";
