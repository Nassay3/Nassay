import { useState, useRef, useEffect } from 'react';
import { Send, X, Bot, User, Sparkles } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useTradingStore } from '@/context/TradingContext';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function ChatPanel({ open, onClose }: ChatPanelProps) {
  const { activeSymbol, interval } = useTradingStore();
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: `مرحباً! أنا مساعدك الذكي للتداول. اسألني عن ${activeSymbol} أو المؤشرات.` },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch(`${import.meta.env.BASE_URL}api/openrouter/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'openai/gpt-4o-mini',
          message: `Symbol: ${activeSymbol}, Timeframe: ${interval}. User: ${userMsg}`,
        }),
      });
      const data = await res.json();
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: data.ok ? (data.content || 'No response') : `Error: ${data.error}` },
      ]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err instanceof Error ? err.message : String(err)}` }]);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-[80] w-[380px] bg-[#080808] border-l border-[#161616] shadow-[0_0_40px_rgba(0,0,0,0.7)] flex flex-col animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#161616] bg-[#0d0d0d]">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-[#2962ff]/10">
            <Sparkles size={14} className="text-[#2962ff]" />
          </div>
          <span className="text-sm font-semibold text-foreground">AI Assistant</span>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-md text-[#666] hover:text-foreground hover:bg-[#1a1a1a] transition-colors">
          <X size={16} />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
              m.role === 'user' ? 'bg-[#1a1a1a]' : 'bg-[#2962ff]/10'
            }`}>
              {m.role === 'user' ? <User size={12} className="text-[#aaa]" /> : <Bot size={12} className="text-[#2962ff]" />}
            </div>
            <div className={`max-w-[80%] px-3 py-2 rounded-lg text-[11px] leading-relaxed whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-[#2962ff] text-white'
                : 'bg-[#111111] text-[#d1d4dc] border border-[#1e1e1e]'
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-2">
            <div className="w-6 h-6 rounded-full bg-[#2962ff]/10 flex items-center justify-center shrink-0">
              <Bot size={12} className="text-[#2962ff]" />
            </div>
            <div className="px-3 py-2 rounded-lg bg-[#111111] border border-[#1e1e1e] text-[11px] text-[#666]">
              Thinking…
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[#161616] bg-[#0d0d0d]">
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the chart or indicators…"
            className="flex-1 h-9 text-xs bg-[#111111] border-[#222] text-foreground placeholder:text-[#555] focus-visible:ring-[#2962ff]"
            onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
          />
          <Button
            onClick={send}
            disabled={loading || !input.trim()}
            size="icon"
            className="h-9 w-9 bg-[#2962ff] hover:bg-[#1e4fcf] disabled:opacity-50"
          >
            <Send size={14} />
          </Button>
        </div>
      </div>
    </div>
  );
}
