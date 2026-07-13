import { WebSocketServer, WebSocket } from "ws";
import type { Server } from "http";
import { logger } from "./logger";

const BINANCE_WS = "wss://stream.binance.us:9443/ws";

interface ClientState {
  symbol: string;
  interval: string;
  ws: WebSocket;
}

interface BinanceKlineMessage {
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
          this.clients.set(ws, { symbol, interval, ws });
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
    const streams = [
      `${symbol}@kline_${interval}`,
      `${symbol}@depth`,
      `${symbol}@aggTrade`,
      `${symbol}@ticker`,
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
    const payload = JSON.stringify(msg);
    for (const [ws, state] of this.clients) {
      if (ws.readyState !== WebSocket.OPEN) continue;
      if (!this.matchesClient(msg, state)) continue;
      ws.send(payload);
    }
  }

  private matchesClient(msg: any, state: ClientState): boolean {
    const s = msg.s?.toLowerCase() || msg.S?.toLowerCase() || "";
    if (!s) return false;
    return s === state.symbol;
  }
}
