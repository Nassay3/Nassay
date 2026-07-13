import { useEffect, useMemo, useRef, useState } from 'react';
import { useTradingStore } from '@/context/TradingContext';
import { useListSymbols, getListSymbolsQueryKey } from '@workspace/api-client-react';
import { Search, X, TrendingUp, Star, Clock } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';

interface SymbolPickerProps {
  open: boolean;
  onClose: () => void;
}

const LS_FAVORITES = 'terminal_favorite_symbols';
const LS_RECENTS = 'terminal_recent_symbols';
const MAX_RECENTS = 8;

export default function SymbolPicker({ open, onClose }: SymbolPickerProps) {
  const { activeSymbol, setActiveSymbol } = useTradingStore();
  const [search, setSearch] = useState('');
  const [favorites, setFavorites] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(LS_FAVORITES) || '[]'); } catch { return []; }
  });
  const [recents, setRecents] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(LS_RECENTS) || '[]'); } catch { return []; }
  });
  const inputRef = useRef<HTMLInputElement>(null);

  const symbolsParams = { quote: 'USDT' };
  const { data: symbolsData, isLoading } = useListSymbols(
    symbolsParams,
    { query: { queryKey: getListSymbolsQueryKey(symbolsParams), enabled: open } }
  );

  const allSymbols = useMemo(() =>
    (symbolsData?.symbols || []).map(s => s.symbol).sort(),
  [symbolsData]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return allSymbols;
    return allSymbols.filter(s => s.toLowerCase().includes(q));
  }, [allSymbols, search]);

  useEffect(() => {
    if (open) {
      setSearch('');
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const toggleFavorite = (sym: string) => {
    const next = favorites.includes(sym)
      ? favorites.filter(s => s !== sym)
      : [sym, ...favorites];
    setFavorites(next);
    localStorage.setItem(LS_FAVORITES, JSON.stringify(next));
  };

  const selectSymbol = (sym: string) => {
    if (!sym) return;
    setActiveSymbol(sym);
    const next = [sym, ...recents.filter(s => s !== sym)].slice(0, MAX_RECENTS);
    setRecents(next);
    localStorage.setItem(LS_RECENTS, JSON.stringify(next));
    onClose();
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/60 backdrop-blur-[2px] animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="mt-14 w-[440px] max-h-[70vh] bg-[#080808] border border-[#1e1e1e] rounded-xl shadow-[0_0_40px_rgba(0,0,0,0.7)] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#161616] bg-[#0d0d0d]">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-[#2962ff]/10">
              <TrendingUp size={14} className="text-[#2962ff]" />
            </div>
            <span className="text-sm font-semibold text-foreground tracking-tight">Select Symbol</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-[#666] hover:text-foreground hover:bg-[#1a1a1a] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Search */}
        <div className="p-3 border-b border-[#161616]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#555]" />
            <Input
              ref={inputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symbol, e.g. BTC, ETH..."
              className="pl-9 h-9 text-xs bg-[#111111] border-[#222] text-foreground placeholder:text-[#555] focus-visible:ring-[#2962ff] focus-visible:border-[#2962ff]"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto py-1">
          {isLoading ? (
            <div className="p-3 flex flex-col gap-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full rounded-md" />
              ))}
            </div>
          ) : (
            <>
              {/* Favorites */}
              {!search && favorites.length > 0 && (
                <SymbolGroup
                  title="Favorites"
                  icon={<Star size={12} className="text-[#f9a825]" />}
                  symbols={favorites.filter(s => allSymbols.includes(s))}
                  activeSymbol={activeSymbol}
                  onSelect={selectSymbol}
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
                />
              )}

              {/* Recents */}
              {!search && recents.length > 0 && (
                <SymbolGroup
                  title="Recent"
                  icon={<Clock size={12} className="text-[#00e5ff]" />}
                  symbols={recents.filter(s => allSymbols.includes(s))}
                  activeSymbol={activeSymbol}
                  onSelect={selectSymbol}
                  favorites={favorites}
                  onToggleFavorite={toggleFavorite}
                />
              )}

              {/* All matching */}
              <SymbolGroup
                title={search ? `Search results (${filtered.length})` : 'All USDT pairs'}
                symbols={filtered}
                activeSymbol={activeSymbol}
                onSelect={selectSymbol}
                favorites={favorites}
                onToggleFavorite={toggleFavorite}
              />

              {filtered.length === 0 && !isLoading && (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  No symbols match "{search}".
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-[#161616] bg-[#0d0d0d] text-[10px] text-[#555] flex items-center justify-between">
          <span>{allSymbols.length} USDT pairs available</span>
          <span className="text-[#2962ff]">Binance US</span>
        </div>
      </div>
    </div>
  );
}

function SymbolGroup({
  title,
  icon,
  symbols,
  activeSymbol,
  onSelect,
  favorites,
  onToggleFavorite,
}: {
  title: string;
  icon?: React.ReactNode;
  symbols: string[];
  activeSymbol: string;
  onSelect: (s: string) => void;
  favorites: string[];
  onToggleFavorite: (s: string) => void;
}) {
  if (!symbols.length) return null;
  return (
    <div className="mb-1">
      <div className="px-4 py-1.5 flex items-center gap-2 text-[10px] uppercase tracking-wider font-semibold text-[#555]">
        {icon}
        {title}
      </div>
      {symbols.map(sym => {
        const isActive = sym === activeSymbol;
        const base = sym.replace('USDT', '');
        return (
          <div
            key={sym}
            className={`group flex items-center justify-between px-4 py-2 cursor-pointer transition-colors ${
              isActive ? 'bg-[#2962ff]/10' : 'hover:bg-[#111111]'
            }`}
          >
            <div
              className="flex items-center gap-3 flex-1"
              onClick={() => onSelect(sym)}
            >
              <div className="flex flex-col">
                <span className={`text-xs font-bold font-mono ${isActive ? 'text-[#2962ff]' : 'text-foreground'}`}>
                  {base}
                </span>
                <span className="text-[10px] text-[#555] font-mono">/USDT</span>
              </div>
              {isActive && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2962ff]/20 text-[#2962ff] font-semibold">
                  ACTIVE
                </span>
              )}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); onToggleFavorite(sym); }}
              className={`p-1.5 rounded-md transition-colors ${
                favorites.includes(sym)
                  ? 'text-[#f9a825] hover:text-[#f9a825]/80'
                  : 'text-[#333] hover:text-[#f9a825] hover:bg-[#1a1a1a]'
              }`}
            >
              <Star size={14} fill={favorites.includes(sym) ? 'currentColor' : 'none'} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
