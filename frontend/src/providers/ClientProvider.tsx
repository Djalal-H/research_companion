"use client";

import { createContext, useContext, useMemo, ReactNode } from "react";
import { Client } from "@langchain/langgraph-sdk";

interface ClientContextValue {
  client: Client;
  readMemory: <T>(path: string, signal: AbortSignal) => Promise<T>;
}

const ClientContext = createContext<ClientContextValue | null>(null);

interface ClientProviderProps {
  children: ReactNode;
  deploymentUrl: string;
  apiKey: string;
}

export function ClientProvider({
  children,
  deploymentUrl,
  apiKey,
}: ClientProviderProps) {
  const client = useMemo(() => {
    return new Client({
      apiUrl: deploymentUrl,
      defaultHeaders: {
        "Content-Type": "application/json",
        "X-Api-Key": apiKey,
      },
    });
  }, [deploymentUrl, apiKey]);

  const value = useMemo(
    () => ({
      client,
      readMemory: async <T,>(path: string, signal: AbortSignal): Promise<T> => {
        const response = await fetch(
          `${deploymentUrl.replace(/\/$/, "")}/memory/${path}`,
          {
            signal,
            cache: "no-store",
            headers: { "X-Api-Key": apiKey },
          }
        );
        if (!response.ok)
          throw new Error(
            response.status === 404
              ? "This memory record is unavailable."
              : "Could not load memory details."
          );
        return response.json() as Promise<T>;
      },
    }),
    [client, deploymentUrl, apiKey]
  );

  return (
    <ClientContext.Provider value={value}>{children}</ClientContext.Provider>
  );
}

export function useClient(): Client {
  const context = useContext(ClientContext);

  if (!context) {
    throw new Error("useClient must be used within a ClientProvider");
  }
  return context.client;
}

export function useMemoryClient() {
  const context = useContext(ClientContext);
  if (!context) throw new Error("Memory client requires ClientProvider");
  return context.readMemory;
}
