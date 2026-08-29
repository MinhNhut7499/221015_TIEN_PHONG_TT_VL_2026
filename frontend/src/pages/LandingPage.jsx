import { useState, useEffect, useRef } from "react";
import { useNavigate, Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getPublishedContent, getCmsDraftContent } from '../utils/api';
import {
    Sun, Moon, Rocket, Users, SearchCheck, Layers,
    Eye, ShieldCheck, Globe, BookOpen, Search, ArrowRight, Github, Facebook
} from "lucide-react";

const BoltIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
);
const GoogleIcon = () => (
    <svg width="20" height="20" viewBox="0 0 48 48">
        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
);
const XIcon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.253 5.622 5.911-5.622zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z" />
    </svg>
);

const translations = {
    en: {
        "nav-home": "Home", "nav-features": "Features", "nav-tech": "Tech", "nav-try": "Try Free",
        "hero-badge": "Open-Vocabulary Architecture Recognition",
        "hero-title-1": "Recognise", "hero-title-2": "100+ World Styles",
        "hero-desc": "An AI system that identifies architectural styles from a single photo — across 100+ styles worldwide, including non-Western traditions. No fixed list, no retraining: a 3-judge AI panel reasons over 12 dimensions of structural evidence and abstains honestly when unsure.",
        "hero-cta-1": "Try it now", "hero-cta-2": "Login with Google", "hero-analysis-status": "AI panel reaching consensus...",
        "feat-title": "How the system reasons", "feat-desc": "Instead of one black-box classifier, the system grounds every verdict in evidence, a knowledge base, and an independent panel of AI judges.",
        "feat-1-h": "Open Knowledge Base", "feat-1-p": "106 styles across 12 families (Ancient → Contemporary, including Mughal, Khmer, Byzantine and more). Adding a style is one KB entry — no retraining.",
        "feat-2-h": "3-Judge AI Panel", "feat-2-p": "Gemini, DeepSeek and OpenAI score the candidates independently. Inter-judge agreement decides confidence; low agreement → the system abstains.",
        "feat-3-h": "Evidence in 12 Dimensions", "feat-3-p": "Massing, roof, arches, ornament, material and more — each named feature is shown explicitly, then explained in English and Vietnamese.",
        "feat-4-h": "Hybrid & Honest", "feat-4-p": "Eclectic buildings are reported as a style mixture, not forced into one label. When evidence is thin, the answer is \"uncertain — could be X / Y / Z\".",
        "styles-title": "A World of Styles", "styles-desc": "Representative families from the 106-style knowledge base — Western and non-Western alike.",
        "comp-title": "12 Evidence Dimensions",
        "comp-sub": "What the vision agent observes in every image",
        "tech-title": "Technology Stack",
        "tech-1-h": "Multimodal Vision", "tech-1-p": "Gemini 2.5 Flash fills a structured 12-dimension evidence sheet directly from the image.",
        "tech-2-h": "Multi-LLM Panel + Arbiter", "tech-2-p": "Three independent judges plus a GPT-4o arbiter that reconciles them with the full image.",
        "tech-3-h": "Grounded Knowledge Base", "tech-3-p": "106 styles anchored to Getty AAT, Wikidata and Banister Fletcher — every verdict is traceable.",
        "how-title": "How It Works",
        "how-1-h": "Login via Google", "how-1-p": "Authenticate securely to access your personal analysis history.",
        "how-2-h": "Upload a Photo", "how-2-p": "Upload a building image up to 10MB (JPG, PNG, WEBP).",
        "how-3-h": "Evidence & Panel", "how-3-p": "The vision agent extracts evidence; candidates are grounded in the KB; the 3-judge panel scores them.",
        "how-4-h": "Bilingual Result", "how-4-p": "Get the style mixture, per-style evidence and a full explanation in English and Vietnamese.",
        "cta-title": "Ready to read any building?", "cta-p": "Upload a photo and discover its architectural style — anywhere in the world.", "cta-btn": "Start Analysis",
        "footer-copyright": "© 2026 ArchiAI — Open-Vocabulary Architecture Recognition",
        "footer-privacy": "Privacy", "footer-terms": "Terms",
        // Representative style families (shown on the styles grid)
        "fam-1": "Gothic", "fam-2": "Baroque", "fam-3": "Renaissance",
        "fam-4": "Neoclassical", "fam-5": "Art Nouveau", "fam-6": "Modernism",
        "fam-7": "Mughal", "fam-8": "Khmer", "fam-9": "Byzantine", "fam-10": "Chinese",
        // 12 evidence dimensions
        "dim-massing": "Massing", "dim-roof": "Roof", "dim-supports": "Supports", "dim-arch": "Arches",
        "dim-openings": "Openings", "dim-facade": "Facade", "dim-ornament": "Ornament", "dim-material": "Material",
        "dim-verticals": "Verticals", "dim-vault": "Vault / Dome", "dim-spatial": "Spatial org.", "dim-diagnostic": "Diagnostic"
    },
    vi: {
        "nav-home": "Trang chủ", "nav-features": "Tính năng", "nav-tech": "Công nghệ", "nav-try": "Dùng thử",
        "hero-badge": "Nhận dạng phong cách kiến trúc mở",
        "hero-title-1": "Nhận dạng", "hero-title-2": "100+ phong cách thế giới",
        "hero-desc": "Hệ thống AI nhận diện phong cách kiến trúc từ một bức ảnh — hơn 100 phong cách toàn cầu, bao gồm cả kiến trúc phi phương Tây. Không cần danh sách cố định, không cần huấn luyện lại: hội đồng 3 giám khảo AI suy luận trên 12 chiều bằng chứng và tự từ chối khi chưa chắc chắn.",
        "hero-cta-1": "Thử ngay", "hero-cta-2": "Đăng nhập với Google", "hero-analysis-status": "Hội đồng AI đang đồng thuận...",
        "feat-title": "Hệ thống suy luận thế nào", "feat-desc": "Thay vì một bộ phân loại hộp đen, mỗi kết luận đều dựa trên bằng chứng, cơ sở tri thức và một hội đồng giám khảo AI độc lập.",
        "feat-1-h": "Cơ sở tri thức mở", "feat-1-p": "106 phong cách thuộc 12 họ (Cổ đại → Đương đại, gồm Mughal, Khmer, Byzantine...). Thêm phong cách chỉ là thêm một dòng tri thức — không huấn luyện lại.",
        "feat-2-h": "Hội đồng 3 giám khảo AI", "feat-2-p": "Gemini, DeepSeek và OpenAI chấm điểm ứng viên độc lập. Mức đồng thuận quyết định độ tin cậy; đồng thuận thấp → hệ thống từ chối kết luận.",
        "feat-3-h": "Bằng chứng theo 12 chiều", "feat-3-p": "Khối tổng thể, mái, vòm, trang trí, vật liệu... — từng đặc trưng có tên được hiển thị rõ ràng rồi giải thích song ngữ Anh-Việt.",
        "feat-4-h": "Lai & trung thực", "feat-4-p": "Công trình pha trộn được báo cáo dưới dạng hỗn hợp phong cách, không gán cứng một nhãn. Khi bằng chứng yếu, câu trả lời là \"chưa chắc — có thể là X / Y / Z\".",
        "styles-title": "Một thế giới phong cách", "styles-desc": "Các họ phong cách tiêu biểu trong cơ sở tri thức 106 phong cách — cả phương Tây lẫn phi phương Tây.",
        "comp-title": "12 chiều bằng chứng",
        "comp-sub": "Những gì tác tử thị giác quan sát trong mỗi ảnh",
        "tech-title": "Nền tảng công nghệ",
        "tech-1-h": "Thị giác đa phương thức", "tech-1-p": "Gemini 2.5 Flash điền phiếu bằng chứng 12 chiều có cấu trúc trực tiếp từ ảnh.",
        "tech-2-h": "Hội đồng đa LLM + Trọng tài", "tech-2-p": "Ba giám khảo độc lập cùng một trọng tài GPT-4o hợp nhất ý kiến dựa trên ảnh đầy đủ.",
        "tech-3-h": "Cơ sở tri thức có nguồn", "tech-3-p": "106 phong cách neo theo Getty AAT, Wikidata và Banister Fletcher — mọi kết luận đều truy nguồn được.",
        "how-title": "Cách thức hoạt động",
        "how-1-h": "Đăng nhập Google", "how-1-p": "Xác thực an toàn để truy cập lịch sử phân tích cá nhân.",
        "how-2-h": "Tải ảnh lên", "how-2-p": "Tải lên ảnh công trình tối đa 10MB (JPG, PNG, WEBP).",
        "how-3-h": "Bằng chứng & Hội đồng", "how-3-p": "Tác tử thị giác trích bằng chứng; ứng viên được neo vào cơ sở tri thức; hội đồng 3 giám khảo chấm điểm.",
        "how-4-h": "Kết quả song ngữ", "how-4-p": "Nhận hỗn hợp phong cách, bằng chứng theo từng phong cách và giải thích đầy đủ bằng Anh-Việt.",
        "cta-title": "Sẵn sàng đọc vị mọi công trình?", "cta-p": "Tải ảnh lên và khám phá phong cách kiến trúc — ở bất kỳ đâu trên thế giới.", "cta-btn": "Bắt đầu phân tích",
        "footer-copyright": "© 2026 ArchiAI — Nhận dạng Kiến trúc Mở (Open-Vocabulary)",
        "footer-privacy": "Quyền riêng tư", "footer-terms": "Điều khoản",
        "fam-1": "Gothic", "fam-2": "Baroque", "fam-3": "Phục Hưng",
        "fam-4": "Tân cổ điển", "fam-5": "Art Nouveau", "fam-6": "Hiện đại",
        "fam-7": "Mughal", "fam-8": "Khmer", "fam-9": "Byzantine", "fam-10": "Trung Hoa",
        "dim-massing": "Khối tổng thể", "dim-roof": "Mái", "dim-supports": "Hệ đỡ", "dim-arch": "Vòm cuốn",
        "dim-openings": "Cửa mở", "dim-facade": "Mặt tiền", "dim-ornament": "Trang trí", "dim-material": "Vật liệu",
        "dim-verticals": "Yếu tố đứng", "dim-vault": "Vòm mái", "dim-spatial": "Tổ chức KG", "dim-diagnostic": "Chẩn đoán"
    }
};

const globalCSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }
  body { font-family: 'Inter', sans-serif; }

  .gradient-text {
    background: linear-gradient(90deg, #00d2ff 0%, #9d50bb 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }

  /* scan-line on hero image */
  @keyframes scanMove { 0%,100%{top:0%} 50%{top:calc(100% - 2px)} }
  .scan-line {
    height: 2px;
    background: linear-gradient(to right, transparent, #00d2ff, transparent);
    box-shadow: 0 0 15px #00d2ff;
    position: absolute; width: 100%; z-index: 10;
    animation: scanMove 3s ease-in-out infinite;
  }

  /* CTA button scan effect */
  @keyframes btnScan { 0%{top:-100%} 100%{top:200%} }
  .btn-scan { position: relative; overflow: hidden; }
  .btn-scan-beam {
    pointer-events: none; position: absolute; left:0; width:100%; height:2px;
    background: linear-gradient(to right, transparent, rgba(255,255,255,0.85), transparent);
    box-shadow: 0 0 8px rgba(255,255,255,0.7);
    z-index: 20; display: none;
  }
  .btn-scan:hover .btn-scan-beam { display: block; animation: btnScan 0.75s linear infinite; }

  /* float */
  @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-16px)} }
  .animate-float { animation: float 6s ease-in-out infinite; }

  /* pulse */
  @keyframes pulseSlow { 0%,100%{opacity:1} 50%{opacity:0.45} }
  .animate-pulse-slow { animation: pulseSlow 4s ease-in-out infinite; }

  /* nav link underline slide */
  .nav-link { position:relative; text-decoration:none; padding-bottom:3px; transition:color 0.25s; }
  .nav-link::after {
    content:''; position:absolute; bottom:0; left:50%; right:50%; height:2px; border-radius:999px;
    background: linear-gradient(90deg,#00d2ff,#9d50bb);
    transition: left 0.3s ease, right 0.3s ease;
  }
  .nav-link:hover::after { left:0; right:0; }
  .nav-link:hover { color:#00d2ff !important; }

  /* nav control buttons */
  .nav-ctrl { display:flex; align-items:center; gap:6px; padding:6px 12px; border-radius:8px;
    cursor:pointer; font-weight:700; font-size:12px; transition:all 0.25s; }
  .nav-ctrl:hover { transform:translateY(-2px); box-shadow:0 4px 14px rgba(0,210,255,0.3); }

  /* style cards pop */
  .style-card { transition: all 0.35s cubic-bezier(.34,1.56,.64,1); }
  .style-card:hover { transform: translateY(-8px) scale(1.05); }

  /* comp tags */
  .comp-tag { transition:all 0.3s ease; cursor:default; position:relative; overflow:hidden; }
  .comp-tag:hover { transform:translateY(-4px) scale(1.07); }

  /* tech card left bar */
  .tech-card { position:relative; overflow:hidden; transition:all 0.35s ease; }
  .tech-card::before {
    content:''; position:absolute; left:0; top:0; bottom:0; width:3px;
    background:linear-gradient(180deg,#00d2ff,#9d50bb);
    transform:scaleY(0); transform-origin:bottom; transition:transform 0.35s ease;
    border-radius:0 2px 2px 0;
  }
  .tech-card:hover::before { transform:scaleY(1); }
  .tech-card:hover { transform:translateX(5px); }

  /* animated moving gradient background */
  @keyframes gradientShift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  .animated-gradient {
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-size: 300% 300%;
    animation: gradientShift 20s ease infinite;
  }
  .animated-gradient.dark {
    background-image: linear-gradient(125deg,
      rgba(0,210,255,0.14) 0%, rgba(11,14,20,0) 35%,
      rgba(157,80,187,0.16) 65%, rgba(11,14,20,0) 100%);
  }
  .animated-gradient.light {
    background-image: linear-gradient(125deg,
      rgba(0,210,255,0.10) 0%, rgba(248,250,252,0) 35%,
      rgba(157,80,187,0.10) 65%, rgba(248,250,252,0) 100%);
  }

  /* reveal-on-scroll */
  .reveal {
    opacity: 0; transform: translateY(42px);
    transition: opacity 0.7s ease, transform 0.7s cubic-bezier(.22,1,.36,1);
    will-change: opacity, transform;
  }
  .reveal.visible { opacity: 1; transform: none; }
  @media (prefers-reduced-motion: reduce) {
    .reveal { opacity: 1; transform: none; transition: none; }
    .animated-gradient { animation: none; }
  }
`;

// Translation lookup with an optional CMS override layer: an admin-published
// {en:{...},vi:{...}} map takes precedence over the hardcoded defaults; any key
// the CMS does not override falls back to the built-in copy (backward-compat).
function useT(lang, override) {
    return (k) => {
        const o = override && override[lang] && override[lang][k];
        return (o != null && o !== '') ? o : (translations[lang][k] || k);
    };
}

/* ── ScanButton – all CTA buttons use this ── */
function ScanButton({ children, style, onMouseEnter, onMouseLeave, onClick, gradient = true }) {
    return (
        <button className="btn-scan" onClick={onClick}
            style={{
                position: 'relative', overflow: 'hidden',
                display: 'inline-flex', alignItems: 'center', gap: 10,
                cursor: 'pointer', border: 'none',
                ...(gradient ? { background: 'linear-gradient(to right,#00d2ff,#9d50bb)', color: 'white' } : {}),
                ...style,
            }}
            onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}
        >
            <div className="btn-scan-beam" />
            {children}
        </button>
    );
}

/* ── NAVBAR ── */
function Navbar({ lang, toggleLang, dark, toggleTheme, t }) {
    const navigate = useNavigate();
    const navLinks = [
        { key: 'nav-home', href: '#home' },
        { key: 'nav-features', href: '#features' },
        { key: 'nav-tech', href: '#tech' },
    ];
    const go = (e, href) => { e.preventDefault(); document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' }); };

    return (
        <nav style={{
            position: 'fixed', top: 0, width: '100%', zIndex: 50,
            backdropFilter: 'blur(16px)',
            background: dark ? 'rgba(11,14,20,0.88)' : 'rgba(255,255,255,0.94)',
            borderBottom: `1px solid ${dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.13)'}`,
            padding: '14px 24px',
            boxShadow: dark ? '0 4px 24px rgba(0,0,0,0.5)' : '0 2px 16px rgba(0,0,0,0.09)',
        }}>
            <div style={{ maxWidth: 1280, margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                {/* Logo */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 12, background: 'linear-gradient(135deg,#00d2ff,#9d50bb)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 14px rgba(0,210,255,0.4)' }}>
                        <ShieldCheck size={22} color="white" />
                    </div>
                    <span className="gradient-text" style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.05em' }}>
                        ArchiAI
                    </span>
                </div>

                {/* Links */}
                <div style={{ display: 'flex', gap: 36, fontWeight: 600, fontSize: 15 }}>
                    {navLinks.map(({ key, href }) => (
                        <a key={key} href={href} onClick={e => go(e, href)} className="nav-link"
                            style={{ color: dark ? '#cbd5e1' : '#334155' }}>
                            {t(key)}
                        </a>
                    ))}
                </div>

                {/* Controls */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button className="nav-ctrl" onClick={toggleLang} style={{
                        background: dark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)',
                        border: `1px solid ${dark ? 'rgba(255,255,255,0.16)' : 'rgba(0,0,0,0.16)'}`,
                        color: dark ? '#e2e8f0' : '#1e293b',
                    }}>
                        <Globe size={14} />
                        <span>{lang.toUpperCase()}</span>
                    </button>

                    <button className="nav-ctrl" onClick={toggleTheme} style={{
                        background: dark ? 'rgba(251,191,36,0.1)' : 'rgba(99,102,241,0.1)',
                        border: `1px solid ${dark ? 'rgba(251,191,36,0.35)' : 'rgba(99,102,241,0.35)'}`,
                        color: dark ? '#fbbf24' : '#6366f1',
                    }}>
                        {dark ? <Sun size={14} /> : <Moon size={14} />}
                        <span>{dark ? 'Light' : 'Dark'}</span>
                    </button>

                    <ScanButton style={{
                        padding: '9px 20px', borderRadius: 999, fontWeight: 700, fontSize: 14,
                        boxShadow: '0 4px 14px rgba(0,210,255,0.35)',
                        transition: 'transform 0.2s, box-shadow 0.2s',
                    }}
                        onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.06)'; e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,210,255,0.5)'; }}
                        onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.boxShadow = '0 4px 14px rgba(0,210,255,0.35)'; }}
                        onClick={() => navigate('/login')}
                    >
                        <Rocket size={14} /> {t('nav-try')}
                    </ScanButton>
                </div>
            </div>
        </nav>
    );
}

function BrutalistImage() {
    return (
        <img
            src="/brutalism-hero.jpg"
            alt="Brutalist concrete building analysed by the AI"
            loading="eager"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
    );
}

/* ── HERO ── */
function HeroSection({ dark, t }) {
    const navigate = useNavigate();
    return (
        <section id="home" style={{ padding: '128px 24px 80px' }}>
            <div style={{ maxWidth: 1280, margin: '0 auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 56, alignItems: 'center' }}>
                {/* Left */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
                    <div className="animate-pulse-slow" style={{
                        display: 'inline-flex', alignItems: 'center', gap: 8,
                        padding: '5px 14px', borderRadius: 999,
                        border: '1px solid rgba(0,210,255,0.4)', background: 'rgba(0,210,255,0.1)',
                        color: '#00d2ff', fontSize: 13, fontWeight: 600, width: 'fit-content',
                    }}>
                        <span>●</span> {t('hero-badge')}
                    </div>

                    <h1 style={{ fontSize: 62, fontWeight: 800, lineHeight: 1.1, color: dark ? '#f9fafb' : '#0f172a' }}>
                        {t('hero-title-1')}<br />
                        <span className="gradient-text">{t('hero-title-2')}</span>
                    </h1>

                    <p style={{ fontSize: 17, color: dark ? '#94a3b8' : '#475569', maxWidth: 480, lineHeight: 1.8 }}>
                        {t('hero-desc')}
                    </p>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
                        <ScanButton style={{
                            padding: '14px 28px', borderRadius: 16, fontWeight: 700, fontSize: 17,
                            boxShadow: '0 10px 40px rgba(0,210,255,0.35)',
                            transition: 'transform 0.2s',
                        }}
                            onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.07)'}
                            onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                            onClick={() => navigate('/login')}
                        >
                            <BoltIcon /> {t('hero-cta-1')}
                        </ScanButton>

                        <ScanButton gradient={false} style={{
                            padding: '14px 28px', borderRadius: 16, fontSize: 17, fontWeight: 700,
                            border: `1.5px solid ${dark ? '#475569' : '#94a3b8'}`,
                            background: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                            color: dark ? '#e2e8f0' : '#1e293b',
                            transition: 'transform 0.2s, border-color 0.2s, box-shadow 0.2s',
                        }}
                            onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.04)'; e.currentTarget.style.borderColor = '#00d2ff'; e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,210,255,0.2)'; }}
                            onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.borderColor = dark ? '#475569' : '#94a3b8'; e.currentTarget.style.boxShadow = 'none'; }}
                            onClick={() => navigate('/login')}
                        >
                            <GoogleIcon /> {t('hero-cta-2')}
                        </ScanButton>
                    </div>
                </div>

                {/* Right – scanner card */}
                <div className="animate-float" style={{ position: 'relative' }}>
                    <div style={{ position: 'absolute', inset: -20, background: 'linear-gradient(to right,#00d2ff,#9d50bb)', opacity: 0.18, filter: 'blur(60px)', borderRadius: '50%', pointerEvents: 'none' }} />
                    <div style={{
                        position: 'relative', borderRadius: 24, padding: 24,
                        background: dark ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.9)',
                        backdropFilter: 'blur(14px)',
                        border: `1px solid ${dark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.14)'}`,
                        boxShadow: dark ? '0 25px 60px rgba(0,0,0,0.55)' : '0 20px 50px rgba(0,0,0,0.13)',
                    }}>
                        {/* Image */}
                        <div style={{ position: 'relative', borderRadius: 16, overflow: 'hidden', aspectRatio: '4/3', background: '#0d1117' }}>
                            <BrutalistImage />
                            {/* scan line */}
                            <div className="scan-line" />
                            {/* corner brackets */}
                            {[{ t: '8px', l: '8px', bt: 'borderTop', bl: 'borderLeft' },
                            { t: '8px', r: '8px', bt: 'borderTop', bl: 'borderRight' },
                            { b: '8px', l: '8px', bt: 'borderBottom', bl: 'borderLeft' },
                            { b: '8px', r: '8px', bt: 'borderBottom', bl: 'borderRight' }].map((s, i) => (
                                <div key={i} style={{
                                    position: 'absolute', width: 18, height: 18,
                                    top: s.t, bottom: s.b, left: s.l, right: s.r,
                                    [s.bt]: '2px solid #00d2ff', [s.bl]: '2px solid #00d2ff',
                                    opacity: 0.85,
                                }} />
                            ))}
                            {/* badge */}
                            <div style={{ position: 'absolute', top: 12, left: 12 }}>
                                <span style={{
                                    background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(8px)',
                                    color: '#00d2ff', fontSize: 10, padding: '4px 10px', borderRadius: 6,
                                    fontWeight: 800, border: '1px solid rgba(0,210,255,0.45)', letterSpacing: '0.05em',
                                }}>BRUTALISM · 94.2%</span>
                            </div>
                        </div>
                        {/* Progress */}
                        <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                                <span style={{ color: dark ? '#94a3b8' : '#64748b' }}>{t('hero-analysis-status')}</span>
                                <span style={{ color: '#00d2ff', fontWeight: 700 }}>Brutalism Detected</span>
                            </div>
                            <div style={{ height: 7, borderRadius: 999, background: dark ? '#1e293b' : '#e2e8f0', overflow: 'hidden' }}>
                                <div style={{ height: '100%', width: '94%', borderRadius: 999, background: 'linear-gradient(to right,#00d2ff,#9d50bb)', boxShadow: '0 0 10px rgba(0,210,255,0.6)' }} />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}

/* ── FEATURES 2×2 ── */
function FeaturesSection({ dark, t }) {
    const list = [
        { icon: <BookOpen size={22} />, color: '#00d2ff', hKey: 'feat-1-h', pKey: 'feat-1-p' },
        { icon: <Users size={22} />, color: '#9d50bb', hKey: 'feat-2-h', pKey: 'feat-2-p' },
        { icon: <SearchCheck size={22} />, color: '#00d2ff', hKey: 'feat-3-h', pKey: 'feat-3-p' },
        { icon: <Layers size={22} />, color: '#9d50bb', hKey: 'feat-4-h', pKey: 'feat-4-p' },
    ];
    return (
        <section id="features" style={{ padding: '96px 24px', background: dark ? 'rgba(255,255,255,0.025)' : 'rgba(241,245,249,0.95)' }}>
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
                <div style={{ textAlign: 'center', marginBottom: 56 }}>
                    <h2 style={{ fontSize: 36, fontWeight: 700, color: dark ? '#f9fafb' : '#0f172a' }}>{t('feat-title')}</h2>
                    <p style={{ color: dark ? '#94a3b8' : '#475569', maxWidth: 520, margin: '12px auto 0', lineHeight: 1.65 }}>{t('feat-desc')}</p>
                </div>
                {/* 2×2 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 24 }}>
                    {list.map((f, i) => <FeatureCard key={i} icon={f.icon} color={f.color} title={t(f.hKey)} desc={t(f.pKey)} dark={dark} />)}
                </div>
            </div>
        </section>
    );
}

function FeatureCard({ icon, color, title, desc, dark }) {
    const [hov, setHov] = useState(false);
    return (
        <div style={{
            padding: '28px 32px', borderRadius: 20, display: 'flex', flexDirection: 'column', gap: 14,
            cursor: 'pointer', transition: 'all 0.3s ease',
            transform: hov ? 'translateY(-6px)' : 'translateY(0)',
            background: dark ? (hov ? 'rgba(0,0,0,0.45)' : 'rgba(0,0,0,0.28)') : (hov ? '#ffffff' : 'rgba(255,255,255,0.8)'),
            backdropFilter: 'blur(10px)',
            border: hov ? `2px solid ${color}` : `2px solid ${dark ? 'rgba(255,255,255,0.22)' : 'rgba(15,23,42,0.2)'}`,
            boxShadow: hov ? `0 16px 40px -12px ${color}55, 0 0 0 1px ${color}22` : dark ? '0 2px 12px rgba(0,0,0,0.3)' : '0 2px 12px rgba(0,0,0,0.07)',
        }} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
            <div style={{
                width: 50, height: 50, borderRadius: 14,
                background: hov ? color : `${color}22`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: hov ? 'white' : color, transition: 'all 0.3s ease',
                boxShadow: hov ? `0 4px 16px ${color}55` : 'none',
            }}>{icon}</div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: hov ? color : (dark ? '#f1f5f9' : '#0f172a'), transition: 'color 0.3s' }}>{title}</h3>
            <p style={{ color: dark ? '#94a3b8' : '#475569', fontSize: 14, lineHeight: 1.7 }}>{desc}</p>
        </div>
    );
}

/* ── STYLES SECTION ── */
function StylesSection({ dark, t }) {
    const list = [
        { e: '🏰', k: 'fam-1' }, { e: '🏛️', k: 'fam-2' }, { e: '🎨', k: 'fam-3' },
        { e: '⚖️', k: 'fam-4' }, { e: '🌿', k: 'fam-5' }, { e: '🏢', k: 'fam-6' },
        { e: '🕌', k: 'fam-7' }, { e: '🛕', k: 'fam-8' }, { e: '⛪', k: 'fam-9' }, { e: '🏯', k: 'fam-10' },
    ];
    return (
        <section style={{ padding: '96px 24px' }}>
            <div style={{ maxWidth: 1280, margin: '0 auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 48, flexWrap: 'wrap', gap: 16 }}>
                    <div>
                        <h2 style={{ fontSize: 36, fontWeight: 700, color: dark ? '#f9fafb' : '#0f172a' }}>{t('styles-title')}</h2>
                        <p style={{ color: dark ? '#94a3b8' : '#475569', marginTop: 8 }}>{t('styles-desc')}</p>
                    </div>
                    <span style={{ padding: '5px 18px', borderRadius: 999, background: 'rgba(0,210,255,0.12)', color: '#00d2ff', fontSize: 11, fontWeight: 700, border: '1px solid rgba(0,210,255,0.38)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>106 Styles · 12 Families</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 16 }}>
                    {list.map((s, i) => <StyleCard key={i} emoji={s.e} label={t(s.k)} dark={dark} />)}
                </div>
            </div>
        </section>
    );
}

function StyleCard({ emoji, label, dark }) {
    const [hov, setHov] = useState(false);
    return (
        <div className="style-card" style={{
            padding: '24px 16px', borderRadius: 16, textAlign: 'center', cursor: 'default',
            background: dark ? (hov ? 'rgba(0,210,255,0.09)' : 'rgba(255,255,255,0.04)') : (hov ? 'rgba(0,210,255,0.07)' : '#ffffff'),
            backdropFilter: 'blur(8px)',
            border: hov ? '2px solid #00d2ff' : `2px solid ${dark ? 'rgba(255,255,255,0.22)' : 'rgba(15,23,42,0.2)'}`,
            boxShadow: hov ? '0 12px 28px -8px rgba(0,210,255,0.38)' : dark ? '0 2px 8px rgba(0,0,0,0.2)' : '0 2px 8px rgba(0,0,0,0.07)',
            transition: 'border-color 0.3s, box-shadow 0.3s, background 0.3s',
        }} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
            <div style={{ fontSize: 30, marginBottom: 10, opacity: hov ? 1 : 0.65, transform: hov ? 'scale(1.22)' : 'scale(1)', transition: 'all 0.35s cubic-bezier(.34,1.56,.64,1)', display: 'inline-block' }}>{emoji}</div>
            <div style={{ fontWeight: 700, fontSize: 14, color: hov ? '#00d2ff' : (dark ? '#e2e8f0' : '#0f172a'), transition: 'color 0.3s' }}>{label}</div>
        </div>
    );
}

/* ── EVIDENCE DIMENSIONS SECTION ── */
function ComponentsSection({ dark, t }) {
    const keys = ['dim-massing', 'dim-roof', 'dim-supports', 'dim-arch',
        'dim-openings', 'dim-facade', 'dim-ornament', 'dim-material',
        'dim-verticals', 'dim-vault', 'dim-spatial', 'dim-diagnostic'];
    const colors = ['#00d2ff', '#9d50bb', '#00bcd4', '#a855f7',
        '#22d3ee', '#c084fc', '#06b6d4', '#b45cf6', '#38bdf8', '#d946ef', '#0ea5e9', '#a78bfa'];

    return (
        <section style={{
            padding: '96px 24px', position: 'relative', overflow: 'hidden',
            /* always dark bg for this section regardless of mode */
            background: 'linear-gradient(135deg, #0f172a 0%, #1a1f35 60%, #0f172a 100%)',
        }}>
            <div style={{ position: 'absolute', top: 0, right: 0, width: 400, height: 400, background: 'rgba(157,80,187,0.13)', filter: 'blur(120px)', borderRadius: '50%', pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: 0, left: 0, width: 300, height: 300, background: 'rgba(0,210,255,0.09)', filter: 'blur(100px)', borderRadius: '50%', pointerEvents: 'none' }} />
            <div style={{ maxWidth: 1280, margin: '0 auto', textAlign: 'center', position: 'relative', zIndex: 10 }}>
                <h2 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8, color: '#f1f5f9' }}>{t('comp-title')}</h2>
                <p style={{ color: '#64748b', fontSize: 14, marginBottom: 48 }}>{t('comp-sub')}</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 12 }}>
                    {keys.map((k, i) => <CompTag key={i} label={t(k)} accent={colors[i % colors.length]} />)}
                </div>
            </div>
        </section>
    );
}

function CompTag({ label, accent }) {
    const [hov, setHov] = useState(false);
    return (
        <div className="comp-tag" style={{
            padding: '9px 22px', borderRadius: 999, fontSize: 13, fontWeight: 600,
            background: hov ? accent : 'rgba(255,255,255,0.07)',
            color: hov ? '#000' : '#e2e8f0',
            border: `1.5px solid ${hov ? accent : 'rgba(255,255,255,0.18)'}`,
            boxShadow: hov ? `0 6px 20px ${accent}66, 0 0 0 2px ${accent}22` : 'none',
            transition: 'all 0.3s ease',
        }} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
            {label}
        </div>
    );
}

/* ── TECH SECTION ── */
function TechSection({ dark, t }) {
    const techItems = [
        { icon: <Eye size={24} />, color: '#3b82f6', hKey: 'tech-1-h', pKey: 'tech-1-p' },
        { icon: <Users size={24} />, color: '#9d50bb', hKey: 'tech-2-h', pKey: 'tech-2-p' },
        { icon: <BookOpen size={24} />, color: '#22c55e', hKey: 'tech-3-h', pKey: 'tech-3-p' },
    ];
    const steps = [
        { num: 1, color: '#00d2ff', hKey: 'how-1-h', pKey: 'how-1-p' },
        { num: 2, color: '#9d50bb', hKey: 'how-2-h', pKey: 'how-2-p' },
        { num: 3, color: '#00d2ff', hKey: 'how-3-h', pKey: 'how-3-p' },
        { num: 4, color: '#9d50bb', hKey: 'how-4-h', pKey: 'how-4-p' },
    ];
    return (
        <section id="tech" style={{ padding: '96px 24px' }}>
            <div style={{ maxWidth: 1280, margin: '0 auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 80 }}>
                <div>
                    <h2 style={{ fontSize: 36, fontWeight: 700, marginBottom: 32, color: dark ? '#f9fafb' : '#0f172a' }}>{t('tech-title')}</h2>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                        {techItems.map((item, i) => <TechCard key={i} icon={item.icon} color={item.color} title={t(item.hKey)} desc={t(item.pKey)} dark={dark} />)}
                    </div>
                </div>
                <div>
                    <h2 style={{ fontSize: 36, fontWeight: 700, marginBottom: 32, color: dark ? '#f9fafb' : '#0f172a' }}>{t('how-title')}</h2>
                    <div style={{ position: 'relative' }}>
                        <div style={{ position: 'absolute', left: 24, top: 8, bottom: 8, width: 2, background: dark ? '#1e293b' : '#e2e8f0', borderRadius: 2 }} />
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 48 }}>
                            {steps.map((step, i) => (
                                <div key={i} style={{ position: 'relative', paddingLeft: 64 }}>
                                    <div style={{ position: 'absolute', left: 0, width: 48, height: 48, borderRadius: '50%', background: `linear-gradient(135deg,${step.color},${step.color}cc)`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 800, fontSize: 17, boxShadow: `0 4px 16px ${step.color}50` }}>{step.num}</div>
                                    <h4 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: dark ? '#f1f5f9' : '#0f172a' }}>{t(step.hKey)}</h4>
                                    <p style={{ color: dark ? '#94a3b8' : '#475569', lineHeight: 1.65 }}>{t(step.pKey)}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}

function TechCard({ icon, color, title, desc, dark }) {
    const [hov, setHov] = useState(false);
    return (
        <div className="tech-card" style={{
            padding: '22px 24px', borderRadius: 16, display: 'flex', alignItems: 'center', gap: 20,
            background: dark ? (hov ? 'rgba(0,0,0,0.45)' : 'rgba(0,0,0,0.22)') : (hov ? '#ffffff' : 'rgba(255,255,255,0.75)'),
            backdropFilter: 'blur(8px)',
            border: hov ? `2px solid ${color}` : `2px solid ${dark ? 'rgba(255,255,255,0.22)' : 'rgba(15,23,42,0.2)'}`,
            boxShadow: hov ? `0 12px 32px -8px ${color}44` : dark ? '0 2px 10px rgba(0,0,0,0.28)' : '0 2px 10px rgba(0,0,0,0.07)',
        }} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
            <div style={{
                width: 56, height: 56, borderRadius: 14, flexShrink: 0,
                background: hov ? color : `${color}1a`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: hov ? 'white' : color,
                transition: 'all 0.35s ease',
                boxShadow: hov ? `0 4px 16px ${color}55` : 'none',
            }}>{icon}</div>
            <div>
                <h4 style={{ fontWeight: 700, fontSize: 17, color: dark ? '#f1f5f9' : '#0f172a', marginBottom: 4 }}>{title}</h4>
                <p style={{ fontSize: 13, color: dark ? '#94a3b8' : '#475569', lineHeight: 1.6 }}>{desc}</p>
            </div>
        </div>
    );
}

/* ── CTA ── */
function CTASection({ dark, t }) {
    const navigate = useNavigate();
    return (
        <section style={{ padding: '96px 24px' }}>
            <div style={{
                maxWidth: 900, margin: '0 auto', borderRadius: 40, padding: '56px 64px',
                textAlign: 'center', position: 'relative', overflow: 'hidden',
                background: dark ? 'rgba(0,0,0,0.32)' : 'rgba(255,255,255,0.88)',
                backdropFilter: 'blur(14px)',
                border: `1.5px solid ${dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.11)'}`,
                boxShadow: dark ? '0 24px 60px rgba(0,0,0,0.45)' : '0 16px 48px rgba(0,0,0,0.09)',
            }}>
                <div style={{ position: 'absolute', top: -96, left: -96, width: 256, height: 256, background: 'rgba(0,210,255,0.16)', filter: 'blur(60px)', borderRadius: '50%', pointerEvents: 'none' }} />
                <div style={{ position: 'absolute', bottom: -96, right: -96, width: 256, height: 256, background: 'rgba(157,80,187,0.16)', filter: 'blur(60px)', borderRadius: '50%', pointerEvents: 'none' }} />
                <div style={{ position: 'relative', zIndex: 10 }}>
                    <h2 style={{ fontSize: 42, fontWeight: 800, color: dark ? '#f9fafb' : '#0f172a', marginBottom: 14 }}>{t('cta-title')}</h2>
                    <p style={{ fontSize: 18, color: dark ? '#94a3b8' : '#475569', marginBottom: 36 }}>{t('cta-p')}</p>
                    <ScanButton style={{
                        padding: '18px 52px', borderRadius: 16, fontSize: 19, fontWeight: 800,
                        boxShadow: '0 10px 30px rgba(0,210,255,0.32)',
                        transition: 'transform 0.3s, box-shadow 0.3s',
                    }}
                        onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.08)'; e.currentTarget.style.boxShadow = '0 0 40px rgba(0,210,255,0.55)'; }}
                        onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.boxShadow = '0 10px 30px rgba(0,210,255,0.32)'; }}
                        onClick={() => navigate('/login')}
                    >
                        <Search size={18} /> {t('cta-btn')} <ArrowRight size={18} />
                    </ScanButton>
                </div>
            </div>
        </section>
    );
}

/* ── FOOTER ── */
function Footer({ dark, t }) {
    return (
        <footer style={{ padding: '48px 24px', borderTop: `1px solid ${dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.13)'}`, background: dark ? 'transparent' : 'rgba(248,250,252,0.6)' }}>
            <div style={{ maxWidth: 1280, margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'linear-gradient(135deg,#00d2ff,#9d50bb)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <ShieldCheck size={18} color="white" />
                    </div>
                    <span className="gradient-text" style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.05em' }}>
                        ArchiAI
                    </span>
                </div>
                <p style={{ color: dark ? '#64748b' : '#94a3b8', fontSize: 13 }}>{t('footer-copyright')}</p>
                <div style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
                    <Link to="/privacy" style={{ color: dark ? '#94a3b8' : '#64748b', fontSize: 13, textDecoration: 'none', fontWeight: 600 }}>{t('footer-privacy')}</Link>
                    <Link to="/terms" style={{ color: dark ? '#94a3b8' : '#64748b', fontSize: 13, textDecoration: 'none', fontWeight: 600 }}>{t('footer-terms')}</Link>
                </div>
                <div style={{ display: 'flex', gap: 12 }}>
                    {[
                        { label: 'X', icon: <XIcon /> },
                        { label: 'GitHub', icon: <Github size={17} /> },
                        { label: 'Facebook', icon: <Facebook size={17} /> },
                    ].map((s, i) => (
                        <a key={i} href="#" aria-label={s.label} style={{
                            width: 38, height: 38, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            color: dark ? '#64748b' : '#94a3b8', textDecoration: 'none',
                            border: `1.5px solid ${dark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.16)'}`,
                            background: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                            transition: 'all 0.25s ease',
                        }}
                            onMouseEnter={e => { e.currentTarget.style.color = '#00d2ff'; e.currentTarget.style.borderColor = '#00d2ff'; e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = '0 6px 16px rgba(0,210,255,0.3)'; }}
                            onMouseLeave={e => { e.currentTarget.style.color = dark ? '#64748b' : '#94a3b8'; e.currentTarget.style.borderColor = dark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.16)'; e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'none'; }}>
                            {s.icon}
                        </a>
                    ))}
                </div>
            </div>
        </footer>
    );
}

/* ── Reveal-on-scroll wrapper ── */
function Reveal({ children, delay = 0 }) {
    const ref = useRef(null);
    const [visible, setVisible] = useState(false);
    useEffect(() => {
        const el = ref.current;
        if (!el) return undefined;
        const obs = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setVisible(true);
                    obs.unobserve(el);
                }
            },
            { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
        );
        obs.observe(el);
        return () => obs.disconnect();
    }, []);
    return (
        <div ref={ref} className={visible ? 'reveal visible' : 'reveal'} style={{ transitionDelay: `${delay}ms` }}>
            {children}
        </div>
    );
}

/* ── Top scroll-progress bar ── */
function ScrollProgress() {
    const [pct, setPct] = useState(0);
    useEffect(() => {
        const onScroll = () => {
            const doc = document.documentElement;
            const max = doc.scrollHeight - doc.clientHeight;
            setPct(max > 0 ? (doc.scrollTop / max) * 100 : 0);
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
        return () => window.removeEventListener('scroll', onScroll);
    }, []);
    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, height: 3, width: `${pct}%`, zIndex: 60,
            background: 'linear-gradient(90deg,#00d2ff,#9d50bb)',
            boxShadow: '0 0 10px rgba(0,210,255,0.6)',
            transition: 'width 0.1s linear',
        }} />
    );
}

/* ── APP ── */
export default function App() {
    const { theme, lang, toggleTheme, toggleLang } = useApp();
    const dark = theme === 'dark';
    const [cmsOverride, setCmsOverride] = useState(null);
    const [previewLang, setPreviewLang] = useState(null);
    const isPreview = new URLSearchParams(window.location.search).get('preview') === '1';
    // Once a live edit arrives via postMessage, the parent owns the content; a
    // late self-fetch must not clobber it (E3).
    const liveRef = useRef(false);

    // Load admin-managed content (CMS) and merge it over the defaults. In
    // ?preview=1 mode an admin sees the unpublished draft, and live edits are
    // pushed in via postMessage from the CMS editor (no server save).
    useEffect(() => {
        const load = isPreview ? getCmsDraftContent : getPublishedContent;
        load('landing').then((res) => {
            if (res && res.content && !liveRef.current) setCmsOverride(res.content);
        }).catch(() => {});
    }, [isPreview]);

    useEffect(() => {
        if (!isPreview) return;
        const onMsg = (e) => {
            if (e.origin !== window.location.origin) return;
            if (e.data && e.data.source === 'archi-cms') {
                if (e.data.page && e.data.page !== 'landing') return; // ignore other-page edits (E4)
                liveRef.current = true;
                if (e.data.content) setCmsOverride(e.data.content);
                if (e.data.lang) setPreviewLang(e.data.lang);
            }
        };
        window.addEventListener('message', onMsg);
        // Tell the CMS editor we are ready to receive the current edits.
        window.parent && window.parent.postMessage({ source: 'archi-cms-ready' }, window.location.origin);
        return () => window.removeEventListener('message', onMsg);
    }, [isPreview]);

    const t = useT(previewLang || lang, cmsOverride);

    return (
        <>
            <style>{globalCSS}</style>
            <div className={dark ? 'dark' : 'light'} style={{
                position: 'relative',
                minHeight: '100vh',
                background: dark
                    ? 'radial-gradient(at 0% 0%, rgba(0,210,255,0.12) 0, transparent 50%), radial-gradient(at 100% 100%, rgba(157,80,187,0.12) 0, transparent 50%), #0b0e14'
                    : 'radial-gradient(at 0% 0%, rgba(0,210,255,0.06) 0, transparent 45%), radial-gradient(at 100% 100%, rgba(157,80,187,0.06) 0, transparent 45%), #f8fafc',
                color: dark ? '#f9fafb' : '#0f172a',
                fontFamily: "'Inter', sans-serif",
            }}>
                <div className={`animated-gradient ${dark ? 'dark' : 'light'}`} aria-hidden="true" />
                <ScrollProgress />
                <div style={{ position: 'relative', zIndex: 1 }}>
                    <Navbar lang={lang} toggleLang={toggleLang} dark={dark} toggleTheme={toggleTheme} t={t} />
                    <HeroSection dark={dark} t={t} />
                    <Reveal><FeaturesSection dark={dark} t={t} /></Reveal>
                    <Reveal><StylesSection dark={dark} t={t} /></Reveal>
                    <Reveal><ComponentsSection dark={dark} t={t} /></Reveal>
                    <Reveal><TechSection dark={dark} t={t} /></Reveal>
                    <Reveal><CTASection dark={dark} t={t} /></Reveal>
                    <Footer dark={dark} t={t} />
                </div>
            </div>
        </>
    );
}