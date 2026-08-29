import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Sun, Moon, Globe } from 'lucide-react';
import { useApp } from '../context/AppContext';
import SiteFooter from '../components/SiteFooter';

// Contact + canonical site URL used across the legal pages. Replace SITE with the
// real public domain once the app is hosted (app stores require live URLs).
const SUPPORT_EMAIL = 'nhutn7499@gmail.com';
const SITE = 'https://yourdomain.com';
const EFFECTIVE = { en: 'Effective: June 2026', vi: 'Có hiệu lực: Tháng 6/2026' };

const CONTENT = {
    privacy: {
        en: {
            title: 'Privacy Policy',
            updated: EFFECTIVE.en,
            sections: [
                ['Who we are', `ArchiAI ("we") provides AI-assisted recognition of architectural styles. For any privacy request, contact ${SUPPORT_EMAIL}.`],
                ['Data we collect', 'Account: when you sign in with Google we store your name, email and profile picture; when you register with email/password we store your email and a bcrypt hash of your password (never the plaintext). Content: the building images you upload and the analysis results and history they produce. Billing: token and payment transactions (we do NOT store card numbers — see Payments). Technical: your IP address and basic system logs. Your JWT session token is stored in your browser, not in a server cookie.'],
                ['How we use it', 'To authenticate you, run architecture-recognition analyses, keep your history and token wallet, process payments, and secure and debug the service. We do not sell your data and we do not use it for advertising.'],
                ['Third-party AI providers (sub-processors)', 'To analyse an image we send the image to vision AI providers — Google (Gemini), OpenAI and xAI (Grok); a text-only provider (DeepSeek) receives text but no image; VNPay processes payments; an SMTP provider sends verification/reset emails. We do NOT attach your name or email to the image when sending it. By using the service you consent to this processing. Each provider handles data under its own privacy policy.'],
                ['International data transfer', 'These AI providers may process your image and text outside Vietnam (e.g. in the United States or other regions). By using the service you consent to this cross-border transfer.'],
                ['Payments', 'Payments are processed by VNPay on its own PCI-DSS-compliant page. We never receive or store your card or bank credentials. We store only the transaction reference, amount, status and the tokens granted.'],
                ['Data retention', 'Your profile, uploaded images and analysis history are kept until you delete them or delete your account. Anonymised financial records (transactions, ledger) are retained as long as required by accounting/tax law (up to ~10 years) with no personal data attached.'],
                ['Your rights', 'You may access, correct, export, or delete your data, object to or restrict processing, and withdraw consent. You can delete your account and data yourself in the app (Settings → Danger Zone) or by emailing ' + SUPPORT_EMAIL + '. We do not sell personal information.'],
                ['Ownership of your images', 'You keep all rights to the images you upload. You grant us a limited licence to store and process them solely to provide the analysis. We do not claim ownership and do not use them to train models.'],
                ['Children', 'The service is not directed to children under 13 and we do not knowingly collect their data.'],
                ['Security & changes', 'We protect data in transit with TLS, hash passwords with bcrypt, and authenticate with signed JWTs. If a breach affects you we will notify you as required by law. We may update this policy and will post the new effective date here. This policy is governed by the laws of Vietnam.'],
            ],
        },
        vi: {
            title: 'Chính sách Quyền riêng tư',
            updated: EFFECTIVE.vi,
            sections: [
                ['Chúng tôi là ai', `ArchiAI ("chúng tôi") cung cấp dịch vụ nhận dạng phong cách kiến trúc có hỗ trợ AI. Mọi yêu cầu về quyền riêng tư, liên hệ ${SUPPORT_EMAIL}.`],
                ['Dữ liệu chúng tôi thu thập', 'Tài khoản: khi đăng nhập bằng Google, chúng tôi lưu tên, email và ảnh đại diện; khi đăng ký bằng email/mật khẩu, chúng tôi lưu email và bản băm bcrypt của mật khẩu (không bao giờ lưu mật khẩu gốc). Nội dung: ảnh công trình bạn tải lên cùng kết quả và lịch sử phân tích. Thanh toán: giao dịch token/thanh toán (chúng tôi KHÔNG lưu số thẻ — xem mục Thanh toán). Kỹ thuật: địa chỉ IP và nhật ký hệ thống cơ bản. Token phiên (JWT) được lưu trên trình duyệt của bạn, không phải cookie phía máy chủ.'],
                ['Cách chúng tôi sử dụng', 'Để xác thực bạn, chạy phân tích nhận dạng kiến trúc, lưu lịch sử và ví token, xử lý thanh toán, bảo mật và gỡ lỗi dịch vụ. Chúng tôi không bán dữ liệu và không dùng cho quảng cáo.'],
                ['Nhà cung cấp AI bên thứ ba', 'Để phân tích một ảnh, chúng tôi gửi ảnh tới các nhà cung cấp AI thị giác — Google (Gemini), OpenAI và xAI (Grok); một nhà cung cấp chỉ-văn-bản (DeepSeek) nhận văn bản nhưng không nhận ảnh; VNPay xử lý thanh toán; nhà cung cấp SMTP gửi email xác minh/đặt lại mật khẩu. Chúng tôi KHÔNG gắn tên hay email của bạn kèm theo ảnh khi gửi. Khi sử dụng dịch vụ, bạn đồng ý với việc xử lý này. Mỗi nhà cung cấp xử lý dữ liệu theo chính sách riêng của họ.'],
                ['Chuyển dữ liệu xuyên biên giới', 'Các nhà cung cấp AI nói trên có thể xử lý ảnh và văn bản của bạn ngoài Việt Nam (ví dụ tại Hoa Kỳ hoặc khu vực khác). Khi sử dụng dịch vụ, bạn đồng ý với việc chuyển dữ liệu xuyên biên giới này.'],
                ['Thanh toán', 'Thanh toán do VNPay xử lý trên trang đạt chuẩn PCI-DSS của họ. Chúng tôi không bao giờ nhận hay lưu thông tin thẻ/ngân hàng của bạn. Chúng tôi chỉ lưu mã giao dịch, số tiền, trạng thái và số token được cấp.'],
                ['Lưu trữ dữ liệu', 'Hồ sơ, ảnh tải lên và lịch sử phân tích được giữ cho tới khi bạn xóa chúng hoặc xóa tài khoản. Hồ sơ tài chính đã ẩn danh (giao dịch, sổ cái) được giữ theo yêu cầu của luật kế toán/thuế (tối đa ~10 năm), không gắn dữ liệu cá nhân.'],
                ['Quyền của bạn', 'Bạn có thể truy cập, chỉnh sửa, xuất hoặc xóa dữ liệu, phản đối hoặc hạn chế việc xử lý, và rút lại sự đồng ý. Bạn có thể tự xóa tài khoản và dữ liệu trong ứng dụng (Cài đặt → Vùng nguy hiểm) hoặc gửi email tới ' + SUPPORT_EMAIL + '. Chúng tôi không bán thông tin cá nhân.'],
                ['Quyền sở hữu ảnh của bạn', 'Bạn giữ toàn bộ quyền đối với ảnh tải lên. Bạn cấp cho chúng tôi giấy phép hạn chế để lưu trữ và xử lý ảnh chỉ nhằm cung cấp phân tích. Chúng tôi không claim quyền sở hữu và không dùng ảnh để huấn luyện mô hình.'],
                ['Trẻ em', 'Dịch vụ không hướng tới trẻ em dưới 13 tuổi và chúng tôi không cố ý thu thập dữ liệu của trẻ em.'],
                ['Bảo mật & thay đổi', 'Chúng tôi bảo vệ dữ liệu khi truyền bằng TLS, băm mật khẩu bằng bcrypt và xác thực bằng JWT có chữ ký. Nếu xảy ra sự cố rò rỉ ảnh hưởng đến bạn, chúng tôi sẽ thông báo theo quy định pháp luật. Chúng tôi có thể cập nhật chính sách và sẽ đăng ngày hiệu lực mới tại đây. Chính sách này được điều chỉnh bởi pháp luật Việt Nam.'],
            ],
        },
    },
    terms: {
        en: {
            title: 'Terms of Service',
            updated: EFFECTIVE.en,
            sections: [
                ['The service', 'ArchiAI provides AI-assisted recognition of architectural styles. Results are informative and may be uncertain or wrong; they are not professional architectural, structural, historical, legal or financial advice (see our AI Policy).'],
                ['Eligibility', 'You must be at least 13 years old (or the minimum age of digital consent in your country) to use the service.'],
                ['Tokens & plans', 'Each analysis consumes tokens from your wallet. Tokens can be purchased as one-time packs or granted by a subscription tier. Prices and token amounts are shown at checkout and charged in VND.'],
                ['Charging policy', 'Tokens are reserved when an analysis starts. If the analysis fails the tokens are refunded automatically; a degraded run is partially refunded.'],
                ['Refunds', 'Token purchases are generally non-refundable once tokens are credited, except where required by law or at the administrator’s discretion. Refund requests are handled case by case.'],
                ['Acceptable use', 'Do not upload unlawful content or content you have no right to, and do not attempt to disrupt, reverse-engineer or overload the service. Accounts may be deactivated for abuse.'],
                ['Account termination', 'You may delete your account at any time in the app (Settings → Danger Zone). We may suspend or deactivate accounts that violate these terms.'],
                ['Limitation of liability & law', 'The service is provided "as is" without warranty. To the extent permitted by law we are not liable for decisions made based on AI results. These terms are governed by the laws of Vietnam.'],
            ],
        },
        vi: {
            title: 'Điều khoản Dịch vụ',
            updated: EFFECTIVE.vi,
            sections: [
                ['Dịch vụ', 'ArchiAI cung cấp nhận dạng phong cách kiến trúc có hỗ trợ AI. Kết quả mang tính tham khảo và có thể không chắc chắn hoặc sai; đây không phải tư vấn chuyên môn về kiến trúc, kết cấu, lịch sử, pháp lý hay tài chính (xem Chính sách AI).'],
                ['Điều kiện sử dụng', 'Bạn phải đủ ít nhất 13 tuổi (hoặc độ tuổi đồng ý số tối thiểu theo quốc gia của bạn) để dùng dịch vụ.'],
                ['Token & gói', 'Mỗi lần phân tích sẽ trừ token trong ví. Token có thể mua theo gói lẻ một lần hoặc được cấp bởi gói thuê bao. Giá và số token hiển thị khi thanh toán, tính bằng VND.'],
                ['Chính sách tính phí', 'Token được giữ lại khi bắt đầu phân tích. Nếu phân tích lỗi, token được hoàn tự động; lần chạy suy giảm (degraded) được hoàn một phần.'],
                ['Hoàn tiền', 'Việc mua token nhìn chung không hoàn lại sau khi token đã được cộng, trừ khi pháp luật yêu cầu hoặc theo quyết định của quản trị viên. Yêu cầu hoàn tiền được xử lý theo từng trường hợp.'],
                ['Sử dụng hợp lệ', 'Không tải lên nội dung vi phạm pháp luật hoặc nội dung bạn không có quyền, và không cố gây gián đoạn, dịch ngược hay làm quá tải dịch vụ. Tài khoản có thể bị vô hiệu hóa nếu lạm dụng.'],
                ['Chấm dứt tài khoản', 'Bạn có thể xóa tài khoản bất cứ lúc nào trong ứng dụng (Cài đặt → Vùng nguy hiểm). Chúng tôi có thể tạm khóa hoặc vô hiệu hóa tài khoản vi phạm điều khoản.'],
                ['Giới hạn trách nhiệm & luật áp dụng', 'Dịch vụ được cung cấp "nguyên trạng" không bảo đảm. Trong phạm vi pháp luật cho phép, chúng tôi không chịu trách nhiệm cho các quyết định dựa trên kết quả AI. Điều khoản này được điều chỉnh bởi pháp luật Việt Nam.'],
            ],
        },
    },
    dataDeletion: {
        en: {
            title: 'Data Deletion',
            updated: EFFECTIVE.en,
            sections: [
                ['Delete your account in the app', 'Sign in, open your account page and go to the Danger Zone, then choose "Delete account" and confirm. This immediately deactivates the account and removes your data.'],
                ['Or request by email', `If you cannot access the app, email ${SUPPORT_EMAIL} from your registered address asking to delete your account. We complete deletion requests within 30 days.`],
                ['What is deleted', 'Your profile (name, email, picture), all uploaded images and their physical files, and your entire analysis history. Your sign-in identifiers are removed so the account can no longer be used.'],
                ['What is retained (anonymised)', 'Records of financial transactions (payments, token ledger) are kept in anonymised form, with no personal data attached, only for as long as accounting and tax law requires.'],
                ['Important', 'Account deletion is permanent and cannot be undone. If you have an active subscription, deleting the account forfeits the remaining time.'],
            ],
        },
        vi: {
            title: 'Xóa Dữ liệu',
            updated: EFFECTIVE.vi,
            sections: [
                ['Xóa tài khoản ngay trong ứng dụng', 'Đăng nhập, mở trang tài khoản và vào mục Vùng nguy hiểm, chọn "Xóa tài khoản" rồi xác nhận. Thao tác này lập tức vô hiệu hóa tài khoản và xóa dữ liệu của bạn.'],
                ['Hoặc yêu cầu qua email', `Nếu không truy cập được ứng dụng, hãy gửi email tới ${SUPPORT_EMAIL} từ địa chỉ đã đăng ký để yêu cầu xóa tài khoản. Chúng tôi hoàn tất yêu cầu xóa trong vòng 30 ngày.`],
                ['Những gì bị xóa', 'Hồ sơ của bạn (tên, email, ảnh đại diện), toàn bộ ảnh đã tải lên cùng các tệp vật lý của chúng, và toàn bộ lịch sử phân tích. Các định danh đăng nhập bị xóa để tài khoản không thể dùng lại.'],
                ['Những gì được giữ lại (đã ẩn danh)', 'Bản ghi giao dịch tài chính (thanh toán, sổ cái token) được giữ ở dạng ẩn danh, không gắn dữ liệu cá nhân, chỉ trong thời hạn luật kế toán và thuế yêu cầu.'],
                ['Lưu ý quan trọng', 'Việc xóa tài khoản là vĩnh viễn và không thể hoàn tác. Nếu bạn đang có gói thuê bao, việc xóa tài khoản sẽ mất phần thời gian còn lại.'],
            ],
        },
    },
    support: {
        en: {
            title: 'Support',
            updated: EFFECTIVE.en,
            sections: [
                ['How to use ArchiAI', 'Sign in, upload a photo of a building, and the system analyses its architectural style and shows the supporting evidence and your history. Each analysis uses tokens from your wallet.'],
                ['FAQ — Why does it say "uncertain"?', 'When the panel of AI judges does not agree, the system honestly reports low confidence instead of guessing. Try a clearer, front-on photo of the whole building.'],
                ['FAQ — Tokens & payment', 'Tokens are charged per analysis; failed runs are refunded automatically. Buy tokens from the plans page; payment is handled securely by VNPay.'],
                ['FAQ — Delete my account', 'You can delete your account and data anytime from the Danger Zone on your account page. See our Data Deletion page.'],
                ['Contact', `Email us at ${SUPPORT_EMAIL}. We aim to respond within 2–3 business days. Website: ${SITE}.`],
            ],
        },
        vi: {
            title: 'Hỗ trợ',
            updated: EFFECTIVE.vi,
            sections: [
                ['Cách dùng ArchiAI', 'Đăng nhập, tải lên ảnh một công trình, hệ thống sẽ phân tích phong cách kiến trúc và hiển thị bằng chứng cùng lịch sử của bạn. Mỗi lần phân tích sử dụng token trong ví.'],
                ['Hỏi đáp — Vì sao báo "không chắc chắn"?', 'Khi hội đồng giám khảo AI không đồng thuận, hệ thống trung thực báo độ tin cậy thấp thay vì đoán bừa. Hãy thử ảnh rõ nét, chụp chính diện toàn bộ công trình.'],
                ['Hỏi đáp — Token & thanh toán', 'Token được trừ cho mỗi lần phân tích; lần chạy lỗi được hoàn tự động. Mua token ở trang gói; thanh toán được VNPay xử lý an toàn.'],
                ['Hỏi đáp — Xóa tài khoản', 'Bạn có thể xóa tài khoản và dữ liệu bất cứ lúc nào từ mục Vùng nguy hiểm trên trang tài khoản. Xem trang Xóa Dữ liệu.'],
                ['Liên hệ', `Gửi email tới ${SUPPORT_EMAIL}. Chúng tôi cố gắng phản hồi trong 2–3 ngày làm việc. Website: ${SITE}.`],
            ],
        },
    },
    aiPolicy: {
        en: {
            title: 'AI Policy',
            updated: EFFECTIVE.en,
            sections: [
                ['AI-generated results', 'ArchiAI uses large AI models to estimate architectural styles. Results are probabilistic and may be incomplete or incorrect, especially for hybrid, rare, or non-Western buildings.'],
                ['Not professional advice', 'Do not rely on AI results for medical, legal, financial, structural or safety decisions. Always verify important information with a qualified professional. You are responsible for how you use the results.'],
                ['No automated legal decisions', 'The system only describes likely architectural styles. It does not make automated decisions that have legal or similarly significant effects on you.'],
                ['Which AI providers we use', 'Images are sent to vision AI providers — Google (Gemini), OpenAI and xAI (Grok) — and a text-only provider (DeepSeek) for reasoning and translation. See our Privacy Policy for details on data handling and international transfer.'],
            ],
        },
        vi: {
            title: 'Chính sách AI',
            updated: EFFECTIVE.vi,
            sections: [
                ['Kết quả do AI tạo ra', 'ArchiAI dùng các mô hình AI lớn để ước lượng phong cách kiến trúc. Kết quả mang tính xác suất và có thể chưa đầy đủ hoặc không chính xác, nhất là với công trình lai, hiếm, hoặc phi phương Tây.'],
                ['Không phải tư vấn chuyên môn', 'Đừng dựa vào kết quả AI cho các quyết định y tế, pháp lý, tài chính, kết cấu hay an toàn. Luôn xác minh thông tin quan trọng với chuyên gia có chuyên môn. Bạn chịu trách nhiệm về cách sử dụng kết quả.'],
                ['Không có quyết định pháp lý tự động', 'Hệ thống chỉ mô tả các phong cách kiến trúc có khả năng. Hệ thống không đưa ra quyết định tự động có hệ quả pháp lý hoặc tương tự đối với bạn.'],
                ['Các nhà cung cấp AI chúng tôi dùng', 'Ảnh được gửi tới các nhà cung cấp AI thị giác — Google (Gemini), OpenAI và xAI (Grok) — và một nhà cung cấp chỉ-văn-bản (DeepSeek) để suy luận và dịch. Xem Chính sách Quyền riêng tư để biết chi tiết về xử lý dữ liệu và chuyển dữ liệu xuyên biên giới.'],
            ],
        },
    },
};

/**
 * Shared legal page renderer. ``kind`` selects the content block (privacy,
 * terms, dataDeletion, support, aiPolicy). Bilingual + theme-aware via useApp().
 */
export default function LegalPage({ kind }) {
    const { lang, theme, toggleTheme, toggleLang } = useApp();
    const navigate = useNavigate();
    const dark = theme === 'dark';
    const c = (CONTENT[kind] || CONTENT.privacy)[lang] || (CONTENT[kind] || CONTENT.privacy).vi;

    return (
        <div className={`min-h-screen flex flex-col ${dark ? 'bg-[#0b0e14] text-gray-100' : 'bg-white text-slate-900'}`}>
            <header className={`h-16 px-6 flex items-center justify-between border-b ${dark ? 'border-white/10' : 'border-slate-200'}`}>
                <button onClick={() => navigate(-1)} className="flex items-center gap-2 font-semibold hover:text-[#00d2ff] transition-colors">
                    <ArrowLeft size={18} /> {lang === 'vi' ? 'Quay lại' : 'Back'}
                </button>
                <div className="flex items-center gap-2">
                    <button onClick={toggleLang} className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-bold ${dark ? 'border-white/10 bg-white/5' : 'border-slate-300 bg-slate-100'}`}>
                        <Globe size={16} /> {lang === 'en' ? 'EN' : 'VI'}
                    </button>
                    <button onClick={toggleTheme} className={`p-2 rounded-full border ${dark ? 'border-white/10 bg-white/5' : 'border-slate-300 bg-slate-100'}`}>
                        {dark ? <Sun size={18} className="text-yellow-400" /> : <Moon size={18} className="text-blue-600" />}
                    </button>
                </div>
            </header>

            <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-12">
                <h1 className="text-3xl font-black mb-1">{c.title}</h1>
                <p className="text-sm opacity-60 mb-8">{c.updated}</p>
                <div className="space-y-7">
                    {c.sections.map(([h, body], i) => (
                        <section key={i}>
                            <h2 className="text-lg font-bold mb-2">{h}</h2>
                            <p className="leading-relaxed opacity-80 whitespace-pre-line">{body}</p>
                        </section>
                    ))}
                </div>
            </main>

            <SiteFooter />
        </div>
    );
}
