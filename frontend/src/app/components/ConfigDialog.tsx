"use client";

import { useState, useEffect, type FormEvent } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { StandaloneConfig } from "@/lib/config";

interface ConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (config: StandaloneConfig) => void;
  initialConfig?: StandaloneConfig;
}

export function ConfigDialog({
  open,
  onOpenChange,
  onSave,
  initialConfig,
}: ConfigDialogProps) {
  const [deploymentUrl, setDeploymentUrl] = useState(
    initialConfig?.deploymentUrl || ""
  );
  const [assistantId, setAssistantId] = useState(
    initialConfig?.assistantId || ""
  );
  const [langsmithApiKey, setLangsmithApiKey] = useState(
    initialConfig?.langsmithApiKey || ""
  );
  const [error, setError] = useState("");

  useEffect(() => {
    if (open && initialConfig) {
      setDeploymentUrl(initialConfig.deploymentUrl);
      setAssistantId(initialConfig.assistantId);
      setLangsmithApiKey(initialConfig.langsmithApiKey || "");
      setError("");
    }
  }, [open, initialConfig]);

  const handleSave = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!deploymentUrl || !assistantId) {
      setError("Enter a deployment URL and assistant ID to continue.");
      return;
    }

    onSave({
      deploymentUrl,
      assistantId,
      langsmithApiKey: langsmithApiKey || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Assistant connection</DialogTitle>
          <DialogDescription>
            Connect the LangGraph deployment used by this browser. Values are
            saved locally and never added to the conversation.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={handleSave}
          className="grid gap-4"
        >
          {error && (
            <p
              role="alert"
              className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </p>
          )}
          <div className="grid gap-2">
            <Label htmlFor="deploymentUrl">
              Deployment URL <span className="text-destructive">*</span>
            </Label>
            <Input
              id="deploymentUrl"
              type="url"
              placeholder="https://<deployment-url>"
              value={deploymentUrl}
              onChange={(e) => {
                setDeploymentUrl(e.target.value);
                setError("");
              }}
              autoComplete="url"
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="assistantId">
              Assistant ID <span className="text-destructive">*</span>
            </Label>
            <Input
              id="assistantId"
              placeholder="<assistant-id>"
              value={assistantId}
              onChange={(e) => {
                setAssistantId(e.target.value);
                setError("");
              }}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="langsmithApiKey">
              LangSmith API Key{" "}
              <span className="text-muted-foreground">(Optional)</span>
            </Label>
            <Input
              id="langsmithApiKey"
              type="password"
              placeholder="lsv2_pt_..."
              value={langsmithApiKey}
              onChange={(e) => setLangsmithApiKey(e.target.value)}
              autoComplete="off"
            />
          </div>
          <DialogFooter className="mt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit">Save connection</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
