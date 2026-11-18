import { useCallback, useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';

/**
 * Shared client/group batch logic: list, create, update, delete with one
 * normalised shape so the Groups and Clients pages stay in lockstep.
 *
 * Backend contracts: GET/POST /{kind}-batches, PATCH/DELETE /{kind}-batches/:id
 * payload uses { group_ids | client_ids } and responses carry the matching
 * ids list + counts.
 */

export type BatchKind = 'group' | 'client';

export type Batch = {
  id: number;
  name: string;
  description: string | null;
  ids: number[];
  itemCount: number;
  campaignCount: number;
  created_at: string | null;
  updated_at: string | null;
};

type RawBatch = {
  id: number;
  name: string;
  description: string | null;
  group_ids?: number[];
  client_ids?: number[];
  group_count?: number;
  client_count?: number;
  campaign_count?: number;
  use_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
};

function normalize(kind: BatchKind, raw: RawBatch): Batch {
  const ids = kind === 'group' ? raw.group_ids ?? [] : raw.client_ids ?? [];
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? null,
    ids: Array.isArray(ids) ? ids : [],
    itemCount: kind === 'group' ? Number(raw.group_count ?? ids.length) : Number(raw.client_count ?? ids.length),
    campaignCount: Number(raw.campaign_count ?? raw.use_count ?? 0),
    created_at: raw.created_at ?? null,
    updated_at: raw.updated_at ?? null,
  };
}

function toPayload(kind: BatchKind, name: string, description: string, ids: number[]) {
  return { name, description, ...(kind === 'group' ? { group_ids: ids } : { client_ids: ids }) };
}

export function useBatches(kind: BatchKind) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loaded, setLoaded] = useState(false);
  const base = `/${kind}-batches`;

  const reload = useCallback(async () => {
    const res = await api.get<RawBatch[]>(base);
    const list = Array.isArray(res.data) ? res.data.map((batch) => normalize(kind, batch)) : [];
    setBatches(list);
    setLoaded(true);
    return list;
  }, [base, kind]);

  const create = useCallback(
    async (name: string, description: string, ids: number[]) => {
      const res = await api.post<RawBatch>(base, toPayload(kind, name, description, ids));
      await reload();
      return normalize(kind, res.data);
    },
    [base, kind, reload],
  );

  const update = useCallback(
    async (id: number, name: string, description: string, ids: number[]) => {
      const res = await api.patch<RawBatch>(`${base}/${id}`, toPayload(kind, name, description, ids));
      await reload();
      return normalize(kind, res.data);
    },
    [base, kind, reload],
  );

  const remove = useCallback(
    async (id: number) => {
      await api.delete(`${base}/${id}`);
      await reload();
    },
    [base, reload],
  );

  useEffect(() => {
    reload().catch(() => setLoaded(true));
  }, [reload]);

  return { batches, loaded, reload, create, update, remove };
}

export function batchErrorMessage(err: unknown): string {
  return getErrorMessage(err);
}
