/**
 * Canvas 2D renderer for the live dataflow board.
 *
 * Pure presentation: every node and edge drawn here maps 1:1 onto a registered
 * metric (see ./registry.ts). No data is computed in this file.
 *
 * Rendering budget: <= 50 nodes / <= 200 edges. Excess top-failure steps are
 * collapsed into a single "+N more" aggregate node.
 */

import { useEffect, useMemo, useRef } from 'react';
import { DATAFLOW, DATAFLOW_CAPS } from '../ui';
import { assertMetricRegistered } from './registry';
import { DENSITIES, type DensityKey, type DensitySpec } from './density';
import type { LiveDbPayload } from './types';

type SatelliteNode = { id: string; label: string; value: number; tone: 'ok' | 'warning' | 'error' | 'neutral' };

type LayoutNode = {
  key: string;
  label: string;
  sub?: string;
  percent: number; // gauge fraction 0..1
  tone: 'ok' | 'warning' | 'error' | 'info' | 'neutral';
  x: number;
  y: number;
  w: number;
  h: number;
};

const TONE_COLORS: Record<string, string> = {
  ok: DATAFLOW.healthy,
  warning: DATAFLOW.warning,
  error: DATAFLOW.error,
  info: DATAFLOW.info,
  neutral: DATAFLOW.nodeMuted,
};

function toneFromStatus(status: string | undefined): LayoutNode['tone'] {
  switch (status) {
    case 'ok':
      return 'ok';
    case 'warning':
      return 'warning';
    case 'critical':
    case 'error':
      return 'error';
    case 'idle':
      return 'neutral';
    default:
      return 'info';
  }
}

function toneFromStep(step: string, count: number): SatelliteNode['tone'] {
  if (count === 0) return 'ok';
  return step === 'read_only' ? 'warning' : 'error';
}

function isoProject(col: number, row: number, scale: number): { x: number; y: number } {
  const x = (col - row) * 34 * scale;
  const y = (col + row) * 18 * scale - 24 * scale;
  return { x, y };
}

const POOL_NODE_KEYS: Record<string, string> = {
  whatsapp: 'whatsapp',
  run_queue: 'run_queue',
  writes: 'log_rate',
  db_size: 'db_bytes',
};

function computeLayout(payload: LiveDbPayload, density: DensitySpec): { nodes: LayoutNode[]; edges: Array<[string, string]> } {
  const S = density.scale;
  const NS = density.nodeScale;
  const nodes: LayoutNode[] = [];
  const edges: Array<[string, string]> = [];

  const pools = payload.pools.slice(0, 8);
  // Group satellites by registered key so node ids stay unique: only step=read_only
  // is drawn individually; every other failing step rolls into one aggregate node.
  const readOnly = payload.steps.find((step) => step.step === 'read_only');
  const otherSteps = payload.steps.filter((step) => step.step !== 'read_only');
  const satellites: SatelliteNode[] = [];
  if (readOnly) {
    satellites.push({ id: 'step_read_only', label: 'step=read_only', value: readOnly.count, tone: toneFromStep('read_only', readOnly.count) });
  }
  if (otherSteps.length) {
    satellites.push({
      id: 'step_other',
      label: `+${otherSteps.length} other step(s)`,
      value: otherSteps.reduce((sum, step) => sum + step.count, 0),
      tone: 'warning',
    });
  }

  // Centre hub: the run itself (or nothing yet).
  const counts = payload.runs;
  nodes.push({
    key: 'run_progress',
    label: payload.runs.campaign_name || 'No campaign run',
    sub: payload.runs.run_id ? `run #${payload.runs.run_id} · ${payload.runs.phase ?? 'idle'}` : 'start one from Campaigns',
    percent: counts.total > 0 ? counts.processed / counts.total : 0,
    tone: payload.runs.active ? 'info' : 'neutral',
    x: 0,
    y: 0,
    w: 120 * NS,
    h: 64 * NS,
  });

  // Satellite pool nodes around the hub, in fixed slots.
  const slots: Array<[number, number]> = [
    [0, -2], [2, -2], [2, 0], [2, 2], [0, 2], [-2, 2], [-2, 0], [-2, -2],
  ];
  let satelliteIndex = 0;
  for (const pool of pools) {
    const nodeKey = POOL_NODE_KEYS[pool.id];
    if (!nodeKey) {
      // Unknown pool id from a newer backend: ignored by design.
      continue;
    }
    const [col, row] = slots[satelliteIndex % slots.length];
    satelliteIndex += 1;
    const point = isoProject(col, row, S);
    nodes.push({
      key: nodeKey,
      label: pool.label,
      sub: pool.detail,
      percent: Math.max(0, Math.min(1, pool.percent / 100)),
      tone: toneFromStatus(pool.status),
      x: point.x,
      y: point.y,
      w: 96 * NS,
      h: 52 * NS,
    });
    edges.push(['run_progress', nodeKey]);
  }

  // Failure-step nodes orbit below the hub.
  satellites.slice(0, 8).forEach((satellite, index) => {
    const angle = (-160 + index * 36) * (Math.PI / 180);
    nodes.push({
      key: satellite.id,
      label: satellite.label,
      sub: `${satellite.value} target(s) failed`,
      percent: Math.min(1, satellite.value / 10),
      tone: satellite.tone === 'ok' ? 'neutral' : satellite.tone,
      x: Math.cos(angle) * 155 * S,
      y: Math.sin(angle) * 96 * S + 60 * S,
      w: 96 * NS,
      h: 44 * NS,
    });
    edges.push(['run_progress', satellite.id]);
  });

  // Hard caps (spec F3).
  if (nodes.length > DATAFLOW_CAPS.MAX_NODES) {
    const overflowing = nodes.length - (DATAFLOW_CAPS.MAX_NODES - 1);
    nodes.length = DATAFLOW_CAPS.MAX_NODES - 1;
    nodes.push({
      key: 'run_progress',
      label: `+${overflowing} more`,
      sub: 'collapsed to respect node caps',
      percent: 0,
      tone: 'neutral',
      x: 0,
      y: 170 * S,
      w: 110 * NS,
      h: 40 * NS,
    });
  }
  if (edges.length > DATAFLOW_CAPS.MAX_EDGES) edges.length = DATAFLOW_CAPS.MAX_EDGES;

  return { nodes, edges };
}

function drawDiamond(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.beginPath();
  ctx.moveTo(x, y - h / 2);
  ctx.lineTo(x + w / 2, y);
  ctx.lineTo(x, y + h / 2);
  ctx.lineTo(x - w / 2, y);
  ctx.closePath();
}

function drawGrid(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.save();
  ctx.strokeStyle = DATAFLOW.canvasGrid;
  ctx.lineWidth = 1;
  const step = 34;
  for (let x = -w; x < w * 2; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x - h, h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x + h, h);
    ctx.stroke();
  }
  ctx.restore();
}

function drawGauge(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fraction: number, color: string) {
  ctx.save();
  ctx.lineWidth = 3;
  ctx.strokeStyle = '#222222';
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + Math.max(0, Math.min(1, fraction)) * Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawNode(ctx: CanvasRenderingContext2D, node: LayoutNode, density: DensitySpec) {
  const color = TONE_COLORS[node.tone] ?? DATAFLOW.nodeMuted;
  drawDiamond(ctx, node.x, node.y, node.w, node.h);
  ctx.fillStyle = DATAFLOW.nodeFill;
  ctx.fill();
  ctx.strokeStyle = DATAFLOW.nodeStroke;
  ctx.lineWidth = 1;
  ctx.stroke();

  drawGauge(ctx, node.x, node.y - 2, 12 * density.nodeScale, node.percent, color);

  ctx.fillStyle = DATAFLOW.nodeText;
  ctx.font = `${density.fontLabel}px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(node.label, node.x, node.y + node.h / 2 + 4, node.w + 64 * density.scale);
  if (node.sub) {
    ctx.fillStyle = DATAFLOW.nodeMuted;
    ctx.font = `${density.fontSub}px ui-monospace, monospace`;
    ctx.fillText(node.sub, node.x, node.y + node.h / 2 + 4 + density.fontLabel + 3, node.w + 72 * density.scale);
  }
}

function drawEdge(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, load: number, time: number, phaseOffset: number) {
  const active = load > 0;
  ctx.save();
  ctx.lineWidth = 1 + Math.min(2, load / 34);
  ctx.strokeStyle = active ? DATAFLOW.edgeActive : DATAFLOW.edgeIdle;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  // Slight isometric bend.
  const mx = (x1 + x2) / 2;
  const my = Math.min(y1, y2) - 14;
  ctx.quadraticCurveTo(mx, my, x2, y2);
  ctx.stroke();

  const packetPhase = ((time * (0.6 + load / 40) + phaseOffset) % 1 + 1) % 1;
  const dotX = (1 - packetPhase) * (1 - packetPhase) * x1 + 2 * (1 - packetPhase) * packetPhase * mx + packetPhase * packetPhase * x2;
  const dotY = (1 - packetPhase) * (1 - packetPhase) * y1 + 2 * (1 - packetPhase) * packetPhase * my + packetPhase * packetPhase * y2;
  ctx.fillStyle = active ? DATAFLOW.dot : DATAFLOW.edgeIdle;
  ctx.beginPath();
  ctx.arc(dotX, dotY, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

const POSITIONS_KEY = 'dataflow_node_positions';

function loadPositions(): Record<string, { x: number; y: number }> {
  try {
    const raw = window.localStorage.getItem(POSITIONS_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function savePositions(positions: Record<string, { x: number; y: number }>) {
  try {
    window.localStorage.setItem(POSITIONS_KEY, JSON.stringify(positions));
  } catch {
    // localStorage unavailable; keep positions in memory only.
  }
}

/** Point-in-diamond with a small slack factor (plus label area underneath). */
function hitNode(node: LayoutNode, x: number, y: number): boolean {
  const dx = Math.abs(x - node.x);
  const dy = Math.abs(y - node.y);
  if (dx / (node.w / 2) + dy / (node.h / 2) <= 1.08) return true;
  // Label/sub-label text under the diamond is a wide hit zone.
  const labelH = 44;
  return dx <= (node.w + 64) / 2 && y >= node.y + node.h / 2 && y <= node.y + node.h / 2 + labelH;
}

export default function CanvasSection({
  payload,
  reducedMotion,
  paused,
  density = 'comfortable',
  resetSignal = 0,
}: {
  payload: LiveDbPayload;
  reducedMotion: boolean;
  paused: boolean;
  density?: DensityKey;
  /** Increment to clear dragged positions and restore the computed layout. */
  resetSignal?: number;
}) {
  const spec = DENSITIES[density] ?? DENSITIES.comfortable;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const payloadRef = useRef(payload);
  const pausedRef = useRef(paused);
  const layoutRef = useRef<ReturnType<typeof computeLayout> | null>(null);
  const positionsRef = useRef<Record<string, { x: number; y: number }>>(loadPositions());
  const dragRef = useRef<{ key: string; grabDX: number; grabDY: number } | null>(null);
  const specRef = useRef(spec);
  specRef.current = spec;
  const throughputRef = useRef(0);

  payloadRef.current = payload;
  pausedRef.current = paused;
  throughputRef.current = payload.flows[0]?.sent_per_min ?? 0;

  // Layout only recomputed when the set of ids/values changes, never per frame.
  const layoutKey = useMemo(
    () => [payload.pools.map((p) => `${p.id}:${p.percent}:${p.status}`).join('|'), payload.steps.map((s) => `${s.step}:${s.count}`).join('|'), payload.runs.run_id ?? 0].join('::'),
    [payload],
  );
  const layout = useMemo(() => computeLayout(payload, spec), [layoutKey, density]); // eslint-disable-line react-hooks/exhaustive-deps
  layoutRef.current = layout;

  // Clear dragged positions only when the page asks for it (Reset layout), not on mount.
  const resetSeenRef = useRef(resetSignal);
  useEffect(() => {
    if (resetSeenRef.current === resetSignal) return;
    resetSeenRef.current = resetSignal;
    positionsRef.current = {};
    try {
      window.localStorage.removeItem(POSITIONS_KEY);
    } catch {
      // localStorage unavailable; nothing persisted.
    }
  }, [resetSignal]);

  // Registry contract assertion (dev-time): every drawn node/edge must be registered.
  useEffect(() => {
    if (!import.meta.env.DEV || !layoutRef.current) return;
    for (const node of layoutRef.current.nodes) assertMetricRegistered(node.key);
  }, [layoutKey]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);

    const effectiveNodes = (): LayoutNode[] => {
      const nodes = layoutRef.current?.nodes ?? [];
      const custom = positionsRef.current;
      return nodes.map((node) => (custom[node.key] ? { ...node, x: custom[node.key].x, y: custom[node.key].y } : node));
    };

    const toWorld = (event: PointerEvent): { x: number; y: number } => {
      const rect = canvas.getBoundingClientRect();
      return {
        x: event.clientX - rect.left - rect.width / 2,
        y: event.clientY - rect.top - rect.height / 2,
      };
    };

    const onPointerDown = (event: PointerEvent) => {
      const point = toWorld(event);
      const nodes = effectiveNodes();
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const node = nodes[i];
        if (hitNode(node, point.x, point.y)) {
          dragRef.current = { key: node.key, grabDX: point.x - node.x, grabDY: point.y - node.y };
          try {
            canvas.setPointerCapture(event.pointerId);
          } catch {
            // Older engines; dragging still works while the pointer stays on canvas.
          }
          canvas.style.cursor = 'grabbing';
          event.preventDefault();
          return;
        }
      }
    };
    const onPointerMove = (event: PointerEvent) => {
      const point = toWorld(event);
      const drag = dragRef.current;
      if (drag) {
        positionsRef.current = {
          ...positionsRef.current,
          [drag.key]: { x: point.x - drag.grabDX, y: point.y - drag.grabDY },
        };
        return;
      }
      const hovering = effectiveNodes().some((node) => hitNode(node, point.x, point.y));
      canvas.style.cursor = hovering ? 'grab' : 'default';
    };
    const endDrag = (event: PointerEvent) => {
      if (!dragRef.current) return;
      dragRef.current = null;
      savePositions(positionsRef.current);
      canvas.style.cursor = 'default';
      try {
        canvas.releasePointerCapture(event.pointerId);
      } catch {
        // Already released; nothing to do.
      }
    };

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    let raf = 0;
    let offscreen = false;
    const io = new IntersectionObserver((entries) => {
      offscreen = !(entries[0]?.isIntersecting ?? true);
    });
    io.observe(wrap);

    const tick = (timeMs: number) => {
      raf = window.requestAnimationFrame(tick);
      if ((pausedRef.current || offscreen || document.visibilityState === 'hidden') && !dragRef.current) return;
      const nodes = effectiveNodes();
      const edges = layoutRef.current?.edges ?? [];
      const rect = wrap.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = DATAFLOW.canvasBg;
      ctx.fillRect(0, 0, width, height);
      drawGrid(ctx, width, height);

      const time = reducedMotion ? 0 : timeMs / 1000;
      const totalSent = throughputRef.current;

      ctx.save();
      ctx.translate(width / 2, height / 2);

      // Edges first so nodes sit above them.
      const nodeByKey = new Map(nodes.map((node) => [node.key, node]));
      for (const [from, to] of edges) {
        const target = nodeByKey.get(to);
        if (!target) continue;
        const hub = nodeByKey.get(from) ?? nodes[0];
        drawEdge(ctx, hub.x, hub.y, target.x, target.y, totalSent, time, Math.sin(hashCode(to)) * 10);
      }

      // Nodes.
      for (const node of nodes) {
        drawNode(ctx, node, spec);
      }
      ctx.restore();
    };
    raf = window.requestAnimationFrame(tick);

    return () => {
      window.cancelAnimationFrame(raf);
      observer.disconnect();
      io.disconnect();
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', endDrag);
      canvas.removeEventListener('pointercancel', endDrag);
    };
  }, [reducedMotion]);

  return (
    <div ref={wrapRef} className="h-full w-full overflow-hidden">
      <canvas ref={canvasRef} aria-label="Live flow diagram" className="touch-none select-none" />
    </div>
  );
}

function hashCode(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return hash;
}
