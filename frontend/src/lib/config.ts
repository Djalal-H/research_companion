export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
}

const CONFIG_KEY = "deep-agent-config";
const LOCAL_CONFIG: StandaloneConfig = {
  deploymentUrl: process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:2024",
  assistantId: "research",
};

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;

  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return LOCAL_CONFIG;

  try {
    return JSON.parse(stored);
  } catch {
    return LOCAL_CONFIG;
  }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
