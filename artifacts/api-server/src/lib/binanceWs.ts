import { WebSocketServer, WebSocket } from "ws";
import type { Server } from "http";
import { logger } from "./logger";

const BINANCE_WS = "wss://data-stream.binance.vision:443/ws";

export interface SecondKlineAggregationState {
  interval: string;
  secondBucketOpen: number | null;
  secondKlines: Map<number, BinanceKlineMessage["k"]>;
}

interface ClientState extends SecondKlineAggregationState {
  symbol: string;
  ws: WebSocket;
}

export interface BinanceKlineMessage {
  e: string;
  E: number;
  s: string;
  k: {
    t: number;
    T: number;
    s: string;
    i: string;
    o: string;
    c: string;
    h: string;
    l: string;
    v: string;
    q: string;
    n: number;
    x: boolean;
  };
}

interface BinanceDepthMessage {
  e: string;
  E: number;
  s: string;
  u: number;
  b: Array<[string, string]>;
  a: Array<[string, string]>;
}

interface BinanceTradeMessage {
  e: string;
  E: number;
  s: string;
  p: string;
  q: string;
  T: number;
  m: boolean;
}

interface BinanceTickerMessage {
  e: string;
  E: number;
  s: string;
  c: string;
  p: string;
  P: string;
  h: string;
  l: string;
  v: string;
  q: string;
}

export class BinanceWebSocketBridge {
  private server: WebSocketServer | null = null;
  private clients = new Map<WebSocket, ClientState>();
  private binanceWs: WebSocket | null = null;
  private subscribedStreams = new Set<string>();
  private pendingSubscriptions = new Set<string>();
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;

  constructor(httpServer: Server) {
    this.server = new WebSocketServer({ server: httpServer, path: "/api/ws" });
    this.server.on("connection", (ws) => this.handleClient(ws));
    this.connectBinance();
  }

  private handleClient(ws: WebSocket) {
    logger.info("Frontend client connected to WebSocket");
    ws.on("message", (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        if (msg.type === "subscribe") {
          const symbol = (msg.symbol as string).toLowerCase();
          const interval = (msg.interval as string) || "1m";
          this.clients.set(ws, {
            symbol, interval, ws,
            secondBucketOpen: null,
            secondKlines: new Map(),
          });
          this.updateSubscriptions(symbol, interval);
        }
      } catch (err) {
        logger.error({ err }, "Failed to parse client message");
      }
    });
    ws.on("close", () => {
      this.clients.delete(ws);
      logger.info("Frontend client disconnected");
    });
    ws.on("error", (err) => {
      logger.error({ err }, "Frontend client error");
    });
  }

  private updateSubscriptions(symbol: string, interval: string) {
    const nativeKlineIntervals = new Set([
      "1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M",
    ]);
    const secondsSource = ["5s", "15s", "30s"].includes(interval) ? "1s" : interval;
    const streams = [
      ...(nativeKlineIntervals.has(secondsSource) ? [`${symbol}@kline_${secondsSource}`] : []),
      `${symbol}@depth`, `${symbol}@aggTrade`, `${symbol}@ticker`,
    ];
    for (const stream of streams) {
      if (!this.subscribedStreams.has(stream) && !this.pendingSubscriptions.has(stream)) {
        this.pendingSubscriptions.add(stream);
      }
    }
    this.flushSubscriptions();
  }

  private flushSubscriptions() {
    if (!this.binanceWs || this.binanceWs.readyState !== WebSocket.OPEN) return;
    if (this.pendingSubscriptions.size === 0) return;
    const streams = Array.from(this.pendingSubscriptions);
    const msg = {
      method: "SUBSCRIBE",
      params: streams,
      id: Date.now(),
    };
    this.binanceWs.send(JSON.stringify(msg));
    for (const stream of streams) {
      this.subscribedStreams.add(stream);
    }
    this.pendingSubscriptions.clear();
  }

  private connectBinance() {
    if (this.binanceWs) {
      try { this.binanceWs.terminate(); } catch {}
    }
    const streams = Array.from(this.subscribedStreams).join("/");
    const url = streams ? `${BINANCE_WS}/${streams}` : BINANCE_WS;
    this.binanceWs = new WebSocket(url);

    this.binanceWs.on("open", () => {
      logger.info("Connected to Binance WebSocket");
      this.reconnectDelay = 1000;
      this.flushSubscriptions();
    });

    this.binanceWs.on("message", (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        this.broadcast(msg);
      } catch (err) {
        logger.error({ err }, "Failed to parse Binance message");
      }
    });

    this.binanceWs.on("error", (err) => {
      logger.error({ err }, "Binance WebSocket error");
    });

    this.binanceWs.on("close", (code) => {
      logger.warn({ code }, "Binance WebSocket closed, reconnecting...");
      setTimeout(() => this.connectBinance(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    });
  }

  private broadcast(msg: BinanceKlineMessage | BinanceDepthMessage | BinanceTradeMessage | BinanceTickerMessage | any) {
    if (!this.server) return;
    for (const [ws, state] of this.clients) {
      if (ws.readyState !== WebSocket.OPEN) continue;
      if (msg.e === "kline" && msg.k?.i === "1s" && ["5s", "15s", "30s"].includes(state.interval)) {
        const aggregated = aggregateOneSecondKlineUpdate(msg, state);
        if (aggregated) ws.send(JSON.stringify(aggregated));
        continue;
      }
      if (!this.matchesClient(msg, state)) continue;
      ws.send(JSON.stringify(msg));
    }
  }

  private matchesClient(msg: any, state: ClientState): boolean {
    const s = msg.s?.toLowerCase() || msg.S?.toLowerCase() || "";
    if (!s) return false;
    if (s !== state.symbol) return false;
    if (msg.e === "kline") return msg.k?.i === state.interval;
    return true;
  }
}

export function aggregateOneSecondKlineUpdate(
  message: BinanceKlineMessage,
  state: SecondKlineAggregationState,
): BinanceKlineMessage | null {
  const targetMs = Number.parseInt(state.interval, 10) * 1_000;
  if (!Number.isFinite(targetMs) || targetMs <= 1_000) return null;
  const bucketOpen = Math.floor(message.k.t / targetMs) * targetMs;
  if (state.secondBucketOpen !== bucketOpen) {
    state.secondBucketOpen = bucketOpen;
    state.secondKlines.clear();
  }
  // Binance may update the same 1s candle more than once. Replacement by
  // open-time prevents volume/trade double counting.
  state.secondKlines.set(message.k.t, message.k);
  const source = [...state.secondKlines.values()].sort((a, b) => a.t - b.t);
  return aggregateOneSecondKlineMessages(source, state.interval, message);
}

export function aggregateOneSecondKlineMessages(
  source: BinanceKlineMessage["k"][],
  interval: string,
  envelope: BinanceKlineMessage,
): BinanceKlineMessage | null {
  if (!source.length) return null;
  const targetMs = Number.parseInt(interval, 10) * 1_000;
  if (!Number.isFinite(targetMs) || targetMs <= 1_000) return null;
  const bucketOpen = Math.floor(source[0].t / targetMs) * targetMs;
  const first = source[0];
  const last = source[source.length - 1];
  const sum = (field: "v" | "q") => source.reduce((total, kline) => total + Number(kline[field]), 0);
  return {
    ...envelope,
    k: {
      ...last,
      t: bucketOpen,
      T: bucketOpen + targetMs - 1,
      i: interval,
      o: first.o,
      h: String(Math.max(...source.map((kline) => Number(kline.h)))),
      l: String(Math.min(...source.map((kline) => Number(kline.l)))),
      c: last.c,
      v: String(sum("v")),
      q: String(sum("q")),
      n: source.reduce((total, kline) => total + kline.n, 0),
      x: last.x && last.t + 1_000 >= bucketOpen + targetMs,
    },
  };
}
