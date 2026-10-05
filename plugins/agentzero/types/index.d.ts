export type PendingItem = { id: string; kind: string; sentence: string; provenance: string; createdAt: string | null }
export type Snapshot = { active: number; pending: PendingItem[]; hotSet: { at: string | null; factIds: string[] } | null }
export type HudState = { snapshot: Snapshot | null; error: string | null; stale: boolean }
export type PaneResult = { item: PendingItem; outcome: 'kept' | 'rejected' | 'failed'; message: string }
export type PaneResults = { [id: string]: PaneResult }
export type RawOpen = { [toolUseId: string]: boolean }

declare module 'claude-code' {
  interface PluginState {
    agentzero: { hud: HudState; hotSetError: string | null; paneResults: PaneResults; rawOpen: RawOpen }
  }
}
