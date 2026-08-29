import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MessageCircle, Send, Loader2, Sparkles } from 'lucide-react';
import { askAnalysis } from '../utils/api';

const TXT = {
    en: {
        title: 'Ask about this analysis',
        help: 'Ask why a style was chosen, how it differs from another, or about the evidence.',
        placeholder: 'e.g. Why not Gothic?',
        send: 'Send',
        thinking: 'Thinking…',
        empty: 'Ask a question to start.',
        suggestions: ['Why this style?', 'What is the strongest evidence?', 'How does it differ from the runner-up?']
    },
    vi: {
        title: 'Hỏi về phân tích này',
        help: 'Hỏi vì sao chọn phong cách này, khác phong cách khác ra sao, hay về bằng chứng.',
        placeholder: 'vd: Vì sao không phải Gothic?',
        send: 'Gửi',
        thinking: 'Đang trả lời…',
        empty: 'Đặt một câu hỏi để bắt đầu.',
        suggestions: ['Vì sao là phong cách này?', 'Bằng chứng mạnh nhất là gì?', 'Khác phong cách đứng nhì thế nào?']
    }
};

/**
 * Grounded Q&A chat for a single analysis. The conversation is bound to
 * ``imageId`` (the analysis currently on screen); when ``imageId`` changes
 * (a different history item / a new analysis) the conversation resets so
 * answers never leak across images. Hidden when ``imageId`` is missing.
 *
 * Props:
 *   - imageId: id of the analysis to ask about (null → component hidden)
 *   - theme: 'dark' | 'light'
 *   - lang: 'en' | 'vi'
 */
const AnalysisChat = ({ imageId, theme, lang }) => {
    const dark = theme === 'dark';
    const t = TXT[lang] || TXT.en;
    const [messages, setMessages] = useState([]); // { role: 'user'|'assistant', content }
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const scrollRef = useRef(null);

    // Rebind to the displayed analysis: clear history whenever the image changes.
    useEffect(() => {
        setMessages([]);
        setInput('');
        setError(null);
    }, [imageId]);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

    const send = useCallback(async (question) => {
        const q = (question ?? input).trim();
        if (!q || busy || !imageId) return;
        setInput('');
        setError(null);
        // Send prior turns as history BEFORE appending the new question.
        const history = messages.map((m) => ({ role: m.role, content: m.content }));
        setMessages((prev) => [...prev, { role: 'user', content: q }]);
        setBusy(true);
        try {
            const data = await askAnalysis(imageId, q, history, lang);
            setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy(false);
        }
    }, [input, busy, imageId, messages, lang]);

    if (!imageId) return null;

    const panelBlock = dark ? 'bg-white/5 border-white/10' : 'bg-white border-slate-300 shadow-sm';
    const labelCls = `text-xs font-black uppercase tracking-widest mb-2 ${dark ? 'text-gray-400' : 'text-slate-500'}`;

    return (
        <div className={`p-6 lg:p-8 rounded-[28px] border backdrop-blur-md ${panelBlock}`}>
            <div className="flex items-center gap-2 mb-1">
                <MessageCircle size={18} className="text-[#00d2ff]" />
                <p className={labelCls + ' mb-0'}>{t.title}</p>
            </div>
            <p className="text-xs text-gray-400 mb-4 font-medium">{t.help}</p>

            <div
                ref={scrollRef}
                className={`max-h-72 overflow-y-auto custom-scrollbar space-y-3 mb-4 pr-1 ${messages.length === 0 ? 'hidden' : ''}`}
            >
                {messages.map((m, i) => (
                    <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm font-medium whitespace-pre-wrap leading-relaxed
                            ${m.role === 'user'
                                ? 'bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white'
                                : dark ? 'bg-white/5 border border-white/10 text-gray-200' : 'bg-slate-50 border border-slate-200 text-slate-800'}`}>
                            {m.content}
                        </div>
                    </div>
                ))}
                {busy && (
                    <div className="flex justify-start">
                        <div className={`px-4 py-2.5 rounded-2xl text-sm font-medium flex items-center gap-2 ${dark ? 'bg-white/5 border border-white/10 text-gray-400' : 'bg-slate-50 border border-slate-200 text-slate-500'}`}>
                            <Loader2 size={14} className="animate-spin text-[#00d2ff]" />{t.thinking}
                        </div>
                    </div>
                )}
            </div>

            {messages.length === 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                    {t.suggestions.map((s, i) => (
                        <button
                            key={i}
                            onClick={() => send(s)}
                            disabled={busy}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold border transition-colors disabled:opacity-50
                                ${dark ? 'bg-white/5 border-white/10 hover:bg-[#00d2ff]/10 hover:border-[#00d2ff]/40' : 'bg-slate-50 border-slate-200 hover:bg-blue-50 hover:border-blue-300'}`}
                        >
                            <Sparkles size={12} className="text-[#9d50bb]" />{s}
                        </button>
                    ))}
                </div>
            )}

            {error && <p className="text-xs text-red-400 font-medium mb-2">⚠ {error}</p>}

            <div className="flex items-center gap-2">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
                    placeholder={t.placeholder}
                    disabled={busy}
                    className={`flex-1 px-4 py-3 rounded-2xl border outline-none text-sm font-medium transition-colors
                        ${dark ? 'bg-white/5 border-white/10 focus:border-[#00d2ff]/40 text-gray-100' : 'bg-slate-50 border-slate-200 focus:border-blue-400 text-slate-900'}`}
                />
                <button
                    onClick={() => send()}
                    disabled={busy || !input.trim()}
                    className="px-5 py-3 rounded-2xl bg-gradient-to-r from-[#00d2ff] to-[#9d50bb] text-white font-bold flex items-center gap-2 transition-all hover:scale-[1.03] active:scale-95 disabled:opacity-50 disabled:hover:scale-100"
                >
                    <Send size={16} />
                    <span className="hidden sm:inline">{t.send}</span>
                </button>
            </div>
        </div>
    );
};

export default AnalysisChat;
