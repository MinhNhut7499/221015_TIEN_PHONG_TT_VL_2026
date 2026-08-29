import React, { useState, useEffect, useCallback } from 'react';
import { X, MapPin, Clock, Sparkles, BookOpen, Loader2, ChevronRight } from 'lucide-react';
import { getStyleKnowledge, getStyleKnowledgeById } from '../utils/api';

const TXT = {
    en: {
        title: 'Style knowledge',
        family: 'Family',
        region: 'Region',
        period: 'Period',
        features: 'Defining features',
        description: 'Description',
        references: 'Sources',
        siblings: 'Related styles in this family',
        notFound: 'No knowledge-base entry found for this style.',
        loading: 'Loading…'
    },
    vi: {
        title: 'Tri thức phong cách',
        family: 'Họ phong cách',
        region: 'Khu vực',
        period: 'Thời kỳ',
        features: 'Đặc trưng nhận dạng',
        description: 'Mô tả',
        references: 'Nguồn',
        siblings: 'Phong cách liên quan cùng họ',
        notFound: 'Không tìm thấy phong cách này trong cơ sở tri thức.',
        loading: 'Đang tải…'
    }
};

/**
 * Modal that shows a read-only knowledge card for one architectural style,
 * fetched from the KB (region, period, defining features, description,
 * sources, family + sibling styles). Clicking a sibling navigates in place.
 *
 * Props:
 *   - styleName: free-text style name to open by (initial lookup), or null to close
 *   - theme: 'dark' | 'light'
 *   - lang: 'en' | 'vi'
 *   - onClose: () => void
 */
const StyleKnowledgeCard = ({ styleName, theme, lang, onClose }) => {
    const dark = theme === 'dark';
    const t = TXT[lang] || TXT.en;
    const [card, setCard] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const loadByName = useCallback((name) => {
        setLoading(true);
        setError(null);
        getStyleKnowledge(name)
            .then(setCard)
            .catch(() => setError(t.notFound))
            .finally(() => setLoading(false));
    }, [t.notFound]);

    const loadById = useCallback((id) => {
        setLoading(true);
        setError(null);
        getStyleKnowledgeById(id)
            .then(setCard)
            .catch(() => setError(t.notFound))
            .finally(() => setLoading(false));
    }, [t.notFound]);

    // Open / re-open whenever the requested style name changes.
    useEffect(() => {
        if (!styleName) { setCard(null); setError(null); return; }
        loadByName(styleName);
    }, [styleName, loadByName]);

    if (!styleName) return null;

    const panel = dark ? 'bg-[#0b0e14] border-white/10 text-gray-100' : 'bg-white border-slate-200 text-slate-900';
    const chip = dark ? 'bg-white/5 border-white/10 text-gray-200' : 'bg-slate-100 border-slate-200 text-slate-700';
    const labelCls = `text-[11px] font-black uppercase tracking-widest mb-2 ${dark ? 'text-gray-400' : 'text-slate-500'}`;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
        >
            <div
                className={`relative w-full max-w-2xl max-h-[85vh] overflow-y-auto custom-scrollbar rounded-[28px] border shadow-2xl ${panel}`}
                onClick={(e) => e.stopPropagation()}
            >
                <div className={`sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b backdrop-blur-md ${dark ? 'border-white/10 bg-[#0b0e14]/90' : 'border-slate-200 bg-white/90'}`}>
                    <div className="flex items-center gap-2">
                        <BookOpen size={18} className="text-[#00d2ff]" />
                        <span className={labelCls + ' mb-0'}>{t.title}</span>
                    </div>
                    <button onClick={onClose} className={`p-2 rounded-lg transition-colors ${dark ? 'hover:bg-white/10' : 'hover:bg-slate-100'}`}>
                        <X size={18} />
                    </button>
                </div>

                <div className="p-6 space-y-5">
                    {loading ? (
                        <div className="py-12 flex flex-col items-center gap-3 text-gray-400">
                            <Loader2 size={28} className="animate-spin text-[#00d2ff]" />
                            <span className="font-medium">{t.loading}</span>
                        </div>
                    ) : error ? (
                        <p className="py-10 text-center text-gray-400 font-medium">{error}</p>
                    ) : card ? (
                        <>
                            <div>
                                <h3 className="text-3xl font-black bg-clip-text text-transparent bg-gradient-to-r from-[#00d2ff] to-[#9d50bb]">{card.name}</h3>
                                {card.aliases?.length > 0 && (
                                    <p className="text-sm text-gray-400 mt-1 font-medium">{card.aliases.join(' · ')}</p>
                                )}
                            </div>

                            <div className="flex flex-wrap gap-2">
                                {card.family_name && (
                                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border ${chip}`}>
                                        <Sparkles size={12} className="text-[#9d50bb]" />{t.family}: {card.family_name}
                                    </span>
                                )}
                                {card.region?.length > 0 && (
                                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border ${chip}`}>
                                        <MapPin size={12} className="text-[#00d2ff]" />{card.region.join(', ')}
                                    </span>
                                )}
                                {card.period && (
                                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border ${chip}`}>
                                        <Clock size={12} className="text-[#00d2ff]" />{card.period}
                                    </span>
                                )}
                            </div>

                            {card.description && (
                                <div>
                                    <p className={labelCls}>{t.description}</p>
                                    <p className={`leading-relaxed font-medium ${dark ? 'text-gray-300' : 'text-slate-700'}`}>{card.description}</p>
                                </div>
                            )}

                            {card.defining_features?.length > 0 && (
                                <div>
                                    <p className={labelCls}>{t.features}</p>
                                    <div className="flex flex-wrap gap-2">
                                        {card.defining_features.map((f, i) => (
                                            <span key={i} className={`px-3 py-1 rounded-lg text-sm font-medium border ${chip}`}>{f}</span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {card.siblings?.length > 0 && (
                                <div>
                                    <p className={labelCls}>{t.siblings}</p>
                                    <div className="flex flex-wrap gap-2">
                                        {card.siblings.map((s) => (
                                            <button
                                                key={s.id}
                                                onClick={() => loadById(s.id)}
                                                className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-bold border transition-colors ${dark ? 'bg-white/5 border-white/10 hover:bg-[#00d2ff]/10 hover:border-[#00d2ff]/40' : 'bg-slate-50 border-slate-200 hover:bg-blue-50 hover:border-blue-300'}`}
                                            >
                                                {s.name}<ChevronRight size={12} className="text-gray-400" />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {card.references?.length > 0 && (
                                <div>
                                    <p className={labelCls}>{t.references}</p>
                                    <p className="text-xs text-gray-400 font-medium">{card.references.join(' · ')}</p>
                                </div>
                            )}
                        </>
                    ) : null}
                </div>
            </div>
        </div>
    );
};

export default StyleKnowledgeCard;
