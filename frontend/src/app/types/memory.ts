export type Evidence = {
  id: string;
  role: string;
  content: string;
  recorded_at: string;
  thread_id: string;
  tool_name: string | null;
  source_location: string | null;
};
export type MemoryOperation = {
  id: string;
  interaction_id: string;
  action: string | null;
  target_note_ids: string[];
  input_event_ids: string[];
  reason: string;
  status: string;
  recorded_at: string;
};
type Metadata = { context: string; keywords: string[]; tags: string[] };
export type NoteDetail = {
  id: string;
  project_id: string;
  kind: string;
  origin: string;
  subject: string;
  current_version_id: string;
  versions: {
    version_id: string;
    text: string;
    status: string;
    recorded_at: string;
    event_time: string | null;
    sources: Evidence[];
    metadata: Metadata | null;
    metadata_history: {
      id: string;
      interaction_id: string;
      metadata: Metadata;
      source_ids: string[];
      reason: string;
      recorded_at: string;
    }[];
  }[];
  connections: {
    id: string;
    from_note_id: string;
    to_note_id: string;
    from_version: string;
    to_version: string;
    relation: string;
    status: string;
    reason: string;
    source_ids: string[];
    neighbor_id: string;
    neighbor_text: string;
    neighbor_version_id: string;
    neighbor_status: string;
  }[];
  operations: MemoryOperation[];
  evidence: Evidence[];
};
export type InteractionDetail = {
  id: string;
  project_id: string;
  status: string;
  note_ids: string[];
  operations: MemoryOperation[];
  evidence: Evidence[];
};
