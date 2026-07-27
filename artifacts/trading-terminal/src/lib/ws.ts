export type WsMessageCallback = (msg: any) => void;
type MarketType = 'spot' | 'futures';

class WebSocketManager {
  private ws: WebSocket | null = null;
  private subscribers: Set<WsMessageCallback> = new Set();
  private currentSymbol: string = 'BTCUSDT';
  private currentInterval: string = '1h';
  private currentMarket: MarketType = 'spot';
  private reconnectTimer: number | null = null;

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) return;
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      if (this.reconnectTimer) {
        window.clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      this.subscribe(this.currentSymbol, this.currentInterval, this.currentMarket);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.subscribers.forEach(cb => cb(msg));
      } catch (e) {}
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.reconnectTimer = window.setTimeout(() => this.connect(), 3000);
    };
  }

  subscribeToParams(symbol: string, interval: string, market: MarketType) {
    this.currentSymbol = symbol;
    this.currentInterval = interval;
    this.currentMarket = market;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.subscribe(symbol, interval, market);
    } else {
      this.connect();
    }
  }

  private subscribe(symbol: string, interval: string, market: MarketType) {
    this.ws?.send(JSON.stringify({ type: "subscribe", symbol, interval, market }));
  }

  onMessage(cb: WsMessageCallback) {
    this.subscribers.add(cb);
    return () => this.subscribers.delete(cb);
  }
}

export const wsManager = new WebSocketManager();
