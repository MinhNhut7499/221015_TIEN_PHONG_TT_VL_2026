import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

/**
 * A theme-aware custom dropdown shared across the User and Admin pages.
 *
 * Mirrors the look of the existing Admin status-filter dropdown: a pill trigger
 * with an optional icon + chevron, and an animated, scrollable option panel that
 * closes on outside click. Replaces the plain, unstyled native <select> used by
 * the history/date and dashboard filters.
 *
 * Props:
 *  - value: currently-selected value (compared by string).
 *  - onChange(value): called with the chosen option's value.
 *  - options: [{ value, label }].
 *  - icon: optional lucide icon component shown in the trigger.
 *  - theme: 'dark' | 'light'.
 *  - placeholder: trigger text when nothing matches.
 *  - align: 'left' | 'right' (panel alignment).
 *  - widthClass / panelWidthClass: Tailwind width overrides.
 */
export default function FancySelect({
    value,
    onChange,
    options = [],
    icon: Icon = null,
    theme = 'dark',
    placeholder = '',
    align = 'left',
    widthClass = 'min-w-[120px]',
    panelWidthClass = 'min-w-[150px]',
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    const dark = theme === 'dark';

    useEffect(() => {
        const onClick = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, []);

    const selected = options.find((o) => String(o.value) === String(value));
    const label = selected ? selected.label : placeholder;

    return (
        <div className="relative" ref={ref}>
            <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className={`flex items-center justify-between gap-2 px-3 py-2 rounded-xl border transition-all duration-300 ${widthClass}
                    ${dark
                        ? 'bg-white/5 border-white/10 text-white hover:border-[#00d2ff]/50 hover:bg-white/10'
                        : 'bg-white border-slate-200 text-slate-900 hover:border-blue-400 hover:bg-blue-50/30 shadow-sm'}
                    ${open ? (dark ? 'border-[#00d2ff] ring-2 ring-[#00d2ff]/20' : 'border-blue-500 ring-2 ring-blue-500/10') : ''}`}
            >
                <span className="flex items-center gap-2 min-w-0">
                    {Icon && <Icon size={14} className="opacity-50 flex-shrink-0" />}
                    <span className="text-xs font-bold truncate">{label}</span>
                </span>
                <ChevronDown size={14} className={`transition-transform duration-300 flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
            </button>

            {open && (
                <div className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} mt-2 w-full ${panelWidthClass} max-h-64 overflow-y-auto custom-scrollbar rounded-2xl border backdrop-blur-2xl shadow-2xl z-[100] p-1.5 animate-in slide-in-from-top-2 duration-200
                    ${dark ? 'bg-[#151921]/95 border-white/20 text-white' : 'bg-white/95 border-gray-200 text-slate-900'}`}>
                    {options.map((opt) => {
                        const active = String(opt.value) === String(value);
                        return (
                            <button
                                key={String(opt.value)}
                                type="button"
                                onClick={() => { onChange(opt.value); setOpen(false); }}
                                className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold transition-all duration-150 text-left
                                    ${active
                                        ? (dark ? 'bg-[#00d2ff]/20 text-[#00d2ff]' : 'bg-blue-500/10 text-blue-600')
                                        : (dark ? 'hover:bg-white/5 opacity-80 hover:opacity-100' : 'hover:bg-gray-100')}`}
                            >
                                <span className="truncate">{opt.label}</span>
                                {active && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-current flex-shrink-0" />}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
