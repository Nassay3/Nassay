import { useEffect, useRef, useState } from 'react';
import { useTradingStore, IndicatorSettings, DEFAULT_INDICATOR_SETTINGS, PlotType, PLOT_TYPE_LABELS } from '@/context/TradingContext';
import { Eye, EyeOff, X, Check } from 'lucide-react';
import { Input } from '@/components/ui/input';

interface IndicatorSettingsModalProps {
  open: boolean;
  onClose: () => void;
}

interface IndicatorGroup {
  title: string;
  keys: string[];
}

const GROUPS: IndicatorGroup[] = [
  { title: 'Multi VWAP', keys: ['VWAP 21', 'VWAP 48', 'VWAP 84', 'VWAP 175', 'VWAP 480', 'VWAP 840'] },
  { title: 'Daily VWAP', keys: ['Daily VWAP', 'Prev Daily VWAP', 'Daily VWAP Bands'] },
  { title: 'Weekly VWAP', keys: ['Weekly VWAP', 'Prev Weekly VWAP', 'Weekly VWAP Bands'] },
  { title: 'Sessions', keys: ['Session Asia', 'Session Asia Bands', 'Session London', 'Session London Bands', 'Session NY', 'Session NY Bands', 'Session Daily', 'Session Daily Bands'] },
  { title: 'VWMA Auto', keys: ['VWMA Auto'] },
  { title: 'VWMA MTF Map', keys: ['VWMA MTF'] },
  { title: 'Sub-Panes', keys: ['Dollar Volume', 'Session Volume', 'Relative QV', 'ZScore'] },
];

const PLOT_TYPES: PlotType[] = [
  'line', 'line-broken', 'gradient', 'step', 'step-broken', 'gradient-markers',
  'histogram', 'cross', 'area', 'area-broken', 'columns', 'circles',
];

export default function IndicatorSettingsModal({ open, onClose }: IndicatorSettingsModalProps) {
  const { indicatorSettings, setIndicatorSettings, updateIndicator, resetIndicator } = useTradingStore();
  const [tab, setTab] = useState<'style' | 'visibility'>('style');
  const [draft, setDraft] = useState<IndicatorSettings>(indicatorSettings);
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) setDraft(indicatorSettings);
  }, [open, indicatorSettings]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setActiveDropdown(null);
      }
    };
    window.addEventListener('mousedown', onClick);
    return () => window.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const apply = () => {
    setIndicatorSettings(draft);
    onClose();
  };

  const cancel = () => {
    setDraft(indicatorSettings);
    onClose();
  };

  const updateDraft = (name: string, patch: Partial<IndicatorSettings[string]>) => {
    setDraft(prev => ({ ...prev, [name]: { ...prev[name], ...patch } }));
  };

  const resetAll = () => setDraft(DEFAULT_INDICATOR_SETTINGS);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 backdrop-blur-[2px] animate-in fade-in duration-150" onClick={cancel}>
      <div className="w-[520px] max-h-[80vh] bg-[#080808] border border-[#1e1e1e] rounded-xl shadow-[0_0_60px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#161616] bg-[#0d0d0d]">
          <span className="text-sm font-semibold text-foreground">VWAP ULTRA1 Custom</span>
          <button onClick={cancel} className="p-1.5 rounded-md text-[#666] hover:text-foreground hover:bg-[#1a1a1a] transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#161616]">
          <button
            onClick={() => setTab('style')}
            className={`flex-1 py-2 text-[12px] font-medium transition-colors ${
              tab === 'style' ? 'text-[#2962ff] border-b-2 border-[#2962ff] bg-[#2962ff]/5' : 'text-[#666] hover:text-[#999]'
            }`}
          >
            نمط
          </button>
          <button
            onClick={() => setTab('visibility')}
            className={`flex-1 py-2 text-[12px] font-medium transition-colors ${
              tab === 'visibility' ? 'text-[#2962ff] border-b-2 border-[#2962ff] bg-[#2962ff]/5' : 'text-[#666] hover:text-[#999]'
            }`}
          >
            الظهور
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-1">
          {GROUPS.map(group => (
            <div key={group.title} className="mb-2">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider font-semibold text-[#555]">
                {group.title}
              </div>
              {group.keys.map(key => {
                const setting = draft[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
                if (!setting) return null;
                const isBand = key.includes('Bands');
                return (
                  <div
                    key={key}
                    className="group flex items-center justify-between px-3 py-2 hover:bg-[#101010] transition-colors"
                  >
                    <div className="flex items-center gap-2.5">
                      {/* Plot type dropdown trigger */}
                      <div className="relative" ref={activeDropdown === key ? dropdownRef : undefined}>
                        <button
                          onClick={() => setActiveDropdown(activeDropdown === key ? null : key)}
                          className="flex items-center justify-center w-7 h-7 rounded-md bg-[#111] border border-[#222] hover:border-[#333] transition-colors"
                          title={PLOT_TYPE_LABELS[setting.plotType || 'line'].en}
                        >
                          <PlotTypeIcon type={setting.plotType || 'line'} color={setting.color} />
                        </button>
                        {activeDropdown === key && (
                          <div className="absolute top-full left-0 mt-1 z-50 w-[180px] bg-[#0d0d0d] border border-[#222] rounded-lg shadow-xl overflow-hidden">
                            {PLOT_TYPES.map(type => (
                              <button
                                key={type}
                                onClick={() => { updateDraft(key, { plotType: type }); setActiveDropdown(null); }}
                                className={`flex items-center gap-2 w-full px-3 py-2 text-[11px] text-right hover:bg-[#161616] transition-colors ${
                                  (setting.plotType || 'line') === type ? 'text-[#2962ff]' : 'text-[#aaa]'
                                }`}
                              >
                                <span className="w-4 flex justify-center"><PlotTypeIcon type={type} color={setting.color} /></span>
                                <span>{PLOT_TYPE_LABELS[type].ar}</span>
                                {(setting.plotType || 'line') === type && <Check size={12} className="ml-auto" />}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Color swatch */}
                      <div className="relative w-7 h-7 rounded-md overflow-hidden border border-[#222] shrink-0">
                        <input
                          type="color"
                          value={setting.color}
                          onChange={e => updateDraft(key, { color: e.target.value })}
                          className="absolute -top-1.5 -left-1.5 w-10 h-10 p-0 border-0 cursor-pointer"
                        />
                      </div>

                      <span className={`text-[12px] font-medium ${isBand ? 'text-[#888]' : 'text-foreground'}`}>{key}</span>
                    </div>

                    <div className="flex items-center gap-3">
                      {/* Width slider - only on style tab */}
                      {tab === 'style' && (
                        <div className="hidden sm:flex items-center gap-1.5">
                          <input
                            type="range" min="1" max="3" step="1"
                            value={setting.lineWidth}
                            onChange={e => updateDraft(key, { lineWidth: parseInt(e.target.value) as 1|2|3 })}
                            className="w-16 accent-[#2962ff]"
                          />
                        </div>
                      )}

                      {/* Visibility toggle */}
                      <button
                        onClick={() => updateDraft(key, { visible: !setting.visible })}
                        className={`p-1.5 rounded-md transition-colors ${
                          setting.visible ? 'text-[#2962ff] bg-[#2962ff]/10' : 'text-[#444] hover:text-[#666]'
                        }`}
                      >
                        {setting.visible ? <Eye size={16} /> : <EyeOff size={16} />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#161616] bg-[#0d0d0d]">
          <button
            onClick={resetAll}
            className="px-3 py-1.5 text-[11px] text-[#888] hover:text-foreground transition-colors"
          >
            Reset all
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={cancel}
              className="px-4 py-1.5 text-[11px] font-medium rounded-md border border-[#333] text-[#aaa] hover:bg-[#161616] transition-colors"
            >
              إلغاء
            </button>
            <button
              onClick={apply}
              className="px-4 py-1.5 text-[11px] font-medium rounded-md bg-[#2962ff] text-white hover:bg-[#1e4fcf] transition-colors"
            >
              موافق
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PlotTypeIcon({ type, color }: { type: PlotType; color: string }) {
  switch (type) {
    case 'histogram':
    case 'columns':
      return <span className="block w-1 h-3.5 rounded-sm" style={{ backgroundColor: color }} />;
    case 'area':
    case 'area-broken':
      return <span className="block w-3 h-3 rounded-[1px]" style={{ backgroundColor: color, opacity: 0.5 }} />;
    case 'circles':
      return <span className="block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />;
    case 'line-broken':
    case 'step-broken':
      return <span className="text-[10px] font-mono leading-none" style={{ color }}>− −</span>;
    case 'gradient':
    case 'gradient-markers':
      return <span className="block w-3 h-3 rounded-full bg-gradient-to-r from-transparent to-current" style={{ color }} />;
    case 'step':
      return <svg width="12" height="12" viewBox="0 0 12 12"><polyline points="1,9 4,9 4,6 8,6 8,3 11,3" fill="none" stroke={color} strokeWidth="1.5" /></svg>;
    case 'cross':
      return <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 6h8M6 2v8" stroke={color} strokeWidth="1.5" /></svg>;
    case 'line':
    default:
      return <svg width="12" height="12" viewBox="0 0 12 12"><line x1="1" y1="6" x2="11" y2="6" stroke={color} strokeWidth="1.5" /></svg>;
  }
}
