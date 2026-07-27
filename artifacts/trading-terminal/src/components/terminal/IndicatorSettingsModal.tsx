import { useEffect, useMemo, useState } from 'react';
import {
  ALL_INTERVALS,
  DEFAULT_INDICATOR_SETTINGS,
  IndicatorSettings,
  Interval,
  isVisibleForInterval,
  PlotType,
  useTradingStore,
} from '@/context/TradingContext';
import {
  Check, ChevronDown, ChevronUp, Clock3, Eye, EyeOff,
  RotateCcw, Search, SlidersHorizontal, X,
} from 'lucide-react';

interface IndicatorSettingsModalProps {
  open: boolean;
  onClose: () => void;
  indicatorKey?: string;
}

interface IndicatorGroup {
  title: string;
  description: string;
  keys: string[];
}

const GROUPS: IndicatorGroup[] = [
  { title: 'VWAP متعدد', description: 'متوسطات VWAP المتحركة', keys: ['VWAP 21', 'VWAP 48', 'VWAP 84', 'VWAP 175', 'VWAP 480', 'VWAP 840'] },
  { title: 'VWAP اليومي', description: 'مستويات الجلسة اليومية', keys: ['Daily VWAP', 'Prev Daily VWAP', 'Daily VWAP Bands'] },
  { title: 'VWAP الأسبوعي', description: 'مستويات الأسبوع الحالي والسابق', keys: ['Weekly VWAP', 'Prev Weekly VWAP', 'Weekly VWAP Bands'] },
  { title: 'الجلسات', description: 'آسيا ولندن ونيويورك', keys: ['Session VWAP', 'Session Asia', 'Session Asia Bands', 'Session London', 'Session London Bands', 'Session NY', 'Session NY Bands', 'Session Daily', 'Session Daily Bands'] },
  { title: 'VWMA', description: 'المتوسطات الموزونة بالحجم ومتعددة الفريمات', keys: ['VWMA Auto', 'VWMA MTF'] },
  {
    title: 'النوافذ السفلية',
    description: 'المؤشرات أسفل الشارت الرئيسي',
    keys: [
      'Combined Signal', 'Integrated Dashboard', 'Dollar Volume', 'Session Volume', 'Relative QV',
      'ZScore', 'ZScore 48', 'ZScore 84',
      'ZScore Level -2', 'ZScore Level -1', 'ZScore Level 0', 'ZScore Level 1', 'ZScore Level 2',
    ],
  },
];

const INDICATOR_COMPONENTS: Record<string, string[]> = {
  'Session VWAP': [
    'Session VWAP',
    'Session Asia', 'Session Asia Bands',
    'Session London', 'Session London Bands',
    'Session NY', 'Session NY Bands',
    'Session Daily', 'Session Daily Bands',
  ],
  ZScore: [
    'ZScore', 'ZScore 48', 'ZScore 84',
    'ZScore Level -2', 'ZScore Level -1', 'ZScore Level 0', 'ZScore Level 1', 'ZScore Level 2',
  ],
};

const PLOT_TYPES: Array<{ value: PlotType; label: string }> = [
  { value: 'line', label: 'خط' },
  { value: 'line-broken', label: 'خط بفواصل' },
  { value: 'step', label: 'درجات' },
  { value: 'area', label: 'مساحة' },
  { value: 'histogram', label: 'مدرج' },
  { value: 'columns', label: 'أعمدة' },
  { value: 'circles', label: 'نقاط' },
];

const LINE_STYLES: Array<{ value: 0 | 1 | 2 | 3; label: string }> = [
  { value: 0, label: 'متصل' },
  { value: 1, label: 'متقطع' },
  { value: 2, label: 'منقّط' },
  { value: 3, label: 'متناثر' },
];

const INTERVAL_GROUPS: Array<{ label: string; intervals: Interval[] }> = [
  { label: 'ثوانٍ', intervals: ['5s', '15s', '30s'] },
  { label: 'دقائق', intervals: ['1m', '2m', '5m', '15m', '30m', '45m'] },
  { label: 'ساعات', intervals: ['1h', '4h', '6h', '12h'] },
  { label: 'فريمات عليا', intervals: ['1d', '1w', '1M', '3M'] },
];

const INTRADAY_INTERVALS = ALL_INTERVALS.filter((item) => !['1d', '1w', '1M', '3M'].includes(item));
const HIGHER_INTERVALS: Interval[] = ['1d', '1w', '1M', '3M'];

export default function IndicatorSettingsModal({ open, onClose, indicatorKey }: IndicatorSettingsModalProps) {
  const { indicatorSettings, setIndicatorSettings, interval } = useTradingStore();
  const [draft, setDraft] = useState<IndicatorSettings>(indicatorSettings);
  const [selectedGroup, setSelectedGroup] = useState(GROUPS[0].title);
  const [query, setQuery] = useState('');
  const [enabledOnly, setEnabledOnly] = useState(false);
  const [visibilityOpen, setVisibilityOpen] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(indicatorSettings);
    if (indicatorKey) {
      const targetGroup = GROUPS.find((item) => item.keys.includes(indicatorKey));
      if (targetGroup) setSelectedGroup(targetGroup.title);
      setQuery('');
      setEnabledOnly(false);
      setVisibilityOpen(indicatorKey === 'ZScore' || indicatorKey === 'Session VWAP' ? null : indicatorKey);
    }
  }, [open, indicatorKey, indicatorSettings]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    if (open) window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  const group = GROUPS.find((item) => item.title === selectedGroup) ?? GROUPS[0];
  const settings = useMemo(() => (
    indicatorKey ? (INDICATOR_COMPONENTS[indicatorKey] ?? [indicatorKey]) : group.keys
  ).filter((key) => {
    const setting = draft[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
    return (!enabledOnly || setting?.visible) && key.toLowerCase().includes(query.trim().toLowerCase());
  }), [draft, enabledOnly, group.keys, indicatorKey, query]);

  const updateDraft = (name: string, patch: Partial<IndicatorSettings[string]>) => {
    setDraft((previous) => ({
      ...previous,
      [name]: { ...(previous[name] ?? DEFAULT_INDICATOR_SETTINGS[name]), ...patch },
    }));
  };

  const automaticIntervals = (name: string): Interval[] =>
    ALL_INTERVALS.filter((candidate) => isVisibleForInterval(name, candidate));

  const toggleInterval = (name: string, candidate: Interval) => {
    const setting = draft[name] ?? DEFAULT_INDICATOR_SETTINGS[name];
    const current = setting.visibleIntervals ?? automaticIntervals(name);
    const next = current.includes(candidate)
      ? current.filter((item) => item !== candidate)
      : ALL_INTERVALS.filter((item) => [...current, candidate].includes(item));
    updateDraft(name, { visibleIntervals: next });
  };

  const resetGroup = () => {
    setDraft((previous) => ({
      ...previous,
      ...Object.fromEntries(group.keys.map((key) => [key, DEFAULT_INDICATOR_SETTINGS[key]])),
    }));
  };

  const resetTarget = (name: string) => {
    const keys = INDICATOR_COMPONENTS[name] ?? [name];
    setDraft((previous) => ({
      ...previous,
      ...Object.fromEntries(keys.map((key) => [key, DEFAULT_INDICATOR_SETTINGS[key]])),
    }));
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#020307]/80 p-3 backdrop-blur-sm" onMouseDown={onClose}>
      <section
        dir="rtl"
        className={`flex h-[min(800px,calc(100vh-2rem))] overflow-hidden rounded-2xl border border-[#2a3040] bg-[#0b0e14] shadow-[0_24px_90px_rgba(0,0,0,0.65)] ${
          indicatorKey ? 'w-[min(820px,100%)]' : 'w-[min(1040px,100%)]'
        }`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        {!indicatorKey && <aside className="hidden w-60 shrink-0 border-l border-[#202633] bg-[#0e121b] md:flex md:flex-col">
          <div className="border-b border-[#202633] px-4 py-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-[#eef2ff]">
              <SlidersHorizontal size={16} className="text-[#6793ff]" />
              تخصيص المؤشرات
            </div>
            <p className="mt-1 text-[11px] leading-4 text-[#7e899e]">المظهر والظهور حسب الفريم لكل مؤشر</p>
          </div>
          <nav className="flex-1 space-y-1 overflow-y-auto p-2">
            {GROUPS.map((item) => {
              const active = item.title === group.title;
              const enabled = item.keys.filter((key) => (draft[key] ?? DEFAULT_INDICATOR_SETTINGS[key])?.visible).length;
              return (
                <button
                  key={item.title}
                  onClick={() => setSelectedGroup(item.title)}
                  className={`w-full rounded-lg px-3 py-2.5 text-right transition-colors ${active ? 'bg-[#1a315e] text-[#edf3ff]' : 'text-[#9aa6bb] hover:bg-[#171d29] hover:text-[#dbe5f7]'}`}
                >
                  <div className="flex items-center justify-between gap-2 text-xs font-medium">
                    <span>{item.title}</span>
                    <span className={`rounded-full px-1.5 py-0.5 text-[9px] ${active ? 'bg-[#2d5fbe] text-white' : 'bg-[#202735] text-[#7e899e]'}`}>{enabled}/{item.keys.length}</span>
                  </div>
                  <div className="mt-0.5 truncate text-[10px] text-[#718097]">{item.description}</div>
                </button>
              );
            })}
          </nav>
        </aside>}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-[#202633] px-4 py-3.5">
            <div>
              <h2 className="text-sm font-semibold text-[#eef2ff]" dir={indicatorKey ? 'ltr' : undefined}>{indicatorKey ?? group.title}</h2>
              <p className="mt-0.5 text-[11px] text-[#7e899e]">{indicatorKey ? 'جميع إعدادات هذا المؤشر فقط' : group.description}</p>
            </div>
            <button onClick={onClose} className="rounded-lg p-2 text-[#7e899e] transition-colors hover:bg-[#1b2230] hover:text-white" aria-label="إغلاق">
              <X size={17} />
            </button>
          </header>

          {!indicatorKey && <div className="flex flex-wrap items-center gap-2 border-b border-[#202633] bg-[#0e121b]/60 px-4 py-2.5">
            <label className="flex min-w-[180px] flex-1 items-center gap-2 rounded-lg border border-[#2a3344] bg-[#090c12] px-2.5 py-1.5 text-[#758198] focus-within:border-[#467cf0]">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ابحث عن مؤشر…" className="min-w-0 flex-1 bg-transparent text-xs text-[#e4eafa] outline-none placeholder:text-[#58657a]" />
            </label>
            <button onClick={() => setEnabledOnly((value) => !value)} className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] transition-colors ${enabledOnly ? 'border-[#3d75e8] bg-[#1b376d] text-[#eaf1ff]' : 'border-[#2a3344] text-[#9aa6bb] hover:bg-[#19202c]'}`}>
              {enabledOnly ? <Eye size={13} /> : <EyeOff size={13} />}
              الظاهرة فقط
            </button>
            <button onClick={resetGroup} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] text-[#8895aa] hover:bg-[#19202c] hover:text-[#e5ebf8]">
              <RotateCcw size={13} />استعادة المجموعة
            </button>
          </div>}

          <main className="flex-1 overflow-y-auto p-3 sm:p-4">
            <div className="space-y-2">
              {settings.map((key) => {
                const setting = draft[key] ?? DEFAULT_INDICATOR_SETTINGS[key];
                if (!setting) return null;
                const currentTfVisible = isVisibleForInterval(key, interval, setting);
                const explicitCount = setting.visibleIntervals?.length;
                const visibilityExpanded = visibilityOpen === key;
                const isContainerSetting = key === 'ZScore' || key === 'Session VWAP';
                const isZScoreLevel = key.startsWith('ZScore Level ');

                return (
                  <article key={key} className={`rounded-xl border p-3 transition-colors ${setting.visible ? 'border-[#28354a] bg-[#101621]' : 'border-[#1d2330] bg-[#0d1119] opacity-70'}`}>
                    <div className="grid items-center gap-3 xl:grid-cols-[minmax(155px,1fr)_86px_116px_92px_104px_40px]">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full shadow-[0_0_10px_currentColor]" style={{ color: setting.color, backgroundColor: setting.color }} />
                        <div className="min-w-0">
                          <div className="truncate text-xs font-semibold text-[#e4eafa]" dir="ltr">
                            {key === 'ZScore' ? 'ZScore Pane' : key === 'Session VWAP' ? 'Session VWAP Group' : key}
                          </div>
                          <div className={`mt-0.5 text-[10px] ${currentTfVisible ? 'text-[#758198]' : 'text-[#d69d59]'}`}>
                            {!setting.visible ? 'مخفي' : currentTfVisible ? `ظاهر على ${interval}` : `غير مفعّل على ${interval}`}
                          </div>
                        </div>
                      </div>
                      {isContainerSetting ? (
                        <div className="rounded-lg border border-[#293448] bg-[#0b111b] px-3 py-2 text-[10px] text-[#8290a6] xl:col-span-4">
                          {key === 'ZScore'
                            ? 'إعدادات عامة للنافذة ومكان ظهورها. تنسيق الخطوط والحدود موجود بشكل مستقل في البطاقات التالية.'
                            : 'مفتاح عرض موحّد لكل جلسات VWAP. ويمكن تخصيص لون وخط ونطاق كل جلسة بشكل مستقل في البطاقات التالية.'}
                        </div>
                      ) : (
                        <>
                          <label className="flex items-center gap-1.5 text-[10px] text-[#8895aa]">
                            اللون
                            <input type="color" value={setting.color} onChange={(event) => updateDraft(key, { color: event.target.value })} className="h-7 w-9 cursor-pointer rounded border border-[#354055] bg-transparent p-0.5" />
                          </label>
                          {isZScoreLevel ? (
                            <div className="grid h-8 place-items-center rounded-lg border border-[#303a4d] bg-[#0a0e15] px-2 text-[10px] text-[#8390a5]">حد أفقي</div>
                          ) : (
                            <select value={setting.plotType ?? 'line'} onChange={(event) => updateDraft(key, { plotType: event.target.value as PlotType })} className="h-8 rounded-lg border border-[#303a4d] bg-[#0a0e15] px-2 text-[11px] text-[#dce5f7] outline-none focus:border-[#467cf0]">
                              {PLOT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                            </select>
                          )}
                          <div className="flex rounded-lg border border-[#303a4d] bg-[#0a0e15] p-0.5">
                            {([1, 2, 3] as const).map((width) => (
                              <button key={width} onClick={() => updateDraft(key, { lineWidth: width })} className={`flex-1 rounded-md py-1 text-[10px] ${setting.lineWidth === width ? 'bg-[#2f64ca] text-white' : 'text-[#7e899e] hover:text-white'}`}>{width}px</button>
                            ))}
                          </div>
                          <select value={setting.lineStyle} onChange={(event) => updateDraft(key, { lineStyle: Number(event.target.value) as 0 | 1 | 2 | 3 })} className="h-8 rounded-lg border border-[#303a4d] bg-[#0a0e15] px-2 text-[11px] text-[#dce5f7] outline-none focus:border-[#467cf0]">
                            {LINE_STYLES.map((style) => <option key={style.value} value={style.value}>{style.label}</option>)}
                          </select>
                        </>
                      )}
                      <button onClick={() => updateDraft(key, { visible: !setting.visible })} className={`grid h-8 w-9 place-items-center rounded-lg border transition-colors ${setting.visible ? 'border-[#2f64ca] bg-[#193c7c] text-[#dbe8ff]' : 'border-[#303a4d] text-[#758198] hover:text-white'}`} title={setting.visible ? 'إخفاء' : 'إظهار'}>
                        {setting.visible ? <Eye size={15} /> : <EyeOff size={15} />}
                      </button>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[#202a3a] pt-2.5 text-[10px] text-[#8d9ab0]">
                      {!isContainerSetting && (
                        <>
                          <label className="flex min-w-[185px] flex-1 items-center gap-2">
                            الشفافية
                            <input type="range" min="10" max="100" step="5" value={setting.opacity ?? 100} onChange={(event) => updateDraft(key, { opacity: Number(event.target.value) })} className="min-w-20 flex-1 accent-[#3d75e8]" />
                            <span className="w-8 text-left tabular-nums text-[#c7d2e7]">{setting.opacity ?? 100}%</span>
                          </label>
                          <button onClick={() => updateDraft(key, { showLastValue: !(setting.showLastValue ?? true) })} className={`rounded-md border px-2 py-1 ${setting.showLastValue ?? true ? 'border-[#315eaf] bg-[#17366f] text-[#d8e6ff]' : 'border-[#303a4d] text-[#8390a5]'}`}>القيمة على المقياس</button>
                          <button onClick={() => updateDraft(key, { showPriceLine: !(setting.showPriceLine ?? false) })} className={`rounded-md border px-2 py-1 ${setting.showPriceLine ? 'border-[#315eaf] bg-[#17366f] text-[#d8e6ff]' : 'border-[#303a4d] text-[#8390a5]'}`}>خط القيمة</button>
                        </>
                      )}
                      <button
                        onClick={() => setVisibilityOpen(visibilityExpanded ? null : key)}
                        className={`flex items-center gap-1 rounded-md border px-2 py-1 ${visibilityExpanded ? 'border-[#467cf0] bg-[#1a376c] text-white' : 'border-[#303a4d] text-[#a1acbd] hover:border-[#46536a]'}`}
                      >
                        <Clock3 size={11} />
                        الفريمات: {explicitCount === undefined ? 'تلقائي' : `${explicitCount}/${ALL_INTERVALS.length}`}
                        {visibilityExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                      </button>
                      <button onClick={() => updateDraft(key, DEFAULT_INDICATOR_SETTINGS[key])} className="mr-auto rounded-md px-2 py-1 text-[#8997ac] hover:bg-[#1b2433] hover:text-white">استعادة المؤشر</button>
                    </div>

                    {visibilityExpanded && (
                      <div className="mt-3 rounded-xl border border-[#2a3548] bg-[#090d14] p-3">
                        <div className="mb-3 flex flex-wrap items-center gap-1.5">
                          <span className="ml-1 text-[10px] font-semibold text-[#8592a8]">إعداد سريع</span>
                          <button onClick={() => updateDraft(key, { visibleIntervals: undefined })} className={`rounded-md border px-2 py-1 text-[10px] ${setting.visibleIntervals === undefined ? 'border-[#3970db] bg-[#193b78] text-white' : 'border-[#2d3748] text-[#8e9aae]'}`}>تلقائي</button>
                          <button onClick={() => updateDraft(key, { visibleIntervals: ALL_INTERVALS })} className="rounded-md border border-[#2d3748] px-2 py-1 text-[10px] text-[#a4afc0] hover:border-[#48566d]">الكل</button>
                          <button onClick={() => updateDraft(key, { visibleIntervals: INTRADAY_INTERVALS })} className="rounded-md border border-[#2d3748] px-2 py-1 text-[10px] text-[#a4afc0] hover:border-[#48566d]">داخل اليوم</button>
                          <button onClick={() => updateDraft(key, { visibleIntervals: HIGHER_INTERVALS })} className="rounded-md border border-[#2d3748] px-2 py-1 text-[10px] text-[#a4afc0] hover:border-[#48566d]">يومي فأعلى</button>
                          <button onClick={() => updateDraft(key, { visibleIntervals: [interval] })} className="rounded-md border border-[#2d3748] px-2 py-1 text-[10px] text-[#a4afc0] hover:border-[#48566d]">الفريم الحالي فقط</button>
                          <button onClick={() => updateDraft(key, { visibleIntervals: [] })} className="rounded-md border border-[#482d36] px-2 py-1 text-[10px] text-[#c18a99] hover:border-[#71404e]">لا شيء</button>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                          {INTERVAL_GROUPS.map((intervalGroup) => (
                            <div key={intervalGroup.label}>
                              <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#626f83]">{intervalGroup.label}</div>
                              <div className="flex flex-wrap gap-1">
                                {intervalGroup.intervals.map((candidate) => {
                                  const selected = (setting.visibleIntervals ?? automaticIntervals(key)).includes(candidate);
                                  return (
                                    <button
                                      key={candidate}
                                      onClick={() => toggleInterval(key, candidate)}
                                      className={`min-w-9 rounded-md border px-1.5 py-1 text-[9px] font-semibold transition-colors ${selected ? 'border-[#3c72dd] bg-[#1a3b76] text-[#edf4ff]' : 'border-[#293241] bg-[#0d121b] text-[#647187] hover:text-[#b9c4d5]'}`}
                                    >
                                      {candidate}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
              {!settings.length && (
                <div className="grid min-h-40 place-items-center rounded-xl border border-dashed border-[#2b3445] text-center text-xs text-[#7e899e]">
                  لا توجد مؤشرات مطابقة للبحث.
                </div>
              )}
            </div>
          </main>

          <footer className="flex items-center justify-between border-t border-[#202633] bg-[#0e121b] px-4 py-3">
            <button onClick={() => {
              if (indicatorKey) resetTarget(indicatorKey);
              else setDraft(DEFAULT_INDICATOR_SETTINGS);
            }} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] text-[#8794a9] hover:bg-[#1b2230] hover:text-white">
              <RotateCcw size={13} />{indicatorKey ? 'استعادة المؤشر' : 'استعادة الكل'}
            </button>
            <div className="flex items-center gap-2">
              <button onClick={onClose} className="rounded-lg border border-[#303a4d] px-3 py-1.5 text-[11px] font-medium text-[#b5c0d3] hover:bg-[#1b2230]">إلغاء</button>
              <button onClick={() => { setIndicatorSettings(draft); onClose(); }} className="flex items-center gap-1.5 rounded-lg bg-[#2f64ca] px-3 py-1.5 text-[11px] font-semibold text-white shadow-[0_4px_18px_rgba(47,100,202,0.32)] hover:bg-[#3a73df]">
                <Check size={13} />حفظ التعديلات
              </button>
            </div>
          </footer>
        </div>
      </section>
    </div>
  );
}
