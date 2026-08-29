import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { billingGetTransactionStatus } from '../utils/api';
import SiteFooter from '../components/SiteFooter';

const T = {
  en: {
    processing: 'Confirming your payment…',
    success: 'Payment successful',
    failed: 'Payment failed or was cancelled',
    pending: 'Payment is still being processed. Tokens will be added once confirmed.',
    credited: 'tokens have been added to your wallet.',
    back: 'Back to app',
  },
  vi: {
    processing: 'Đang xác nhận thanh toán…',
    success: 'Thanh toán thành công',
    failed: 'Thanh toán thất bại hoặc đã bị hủy',
    pending: 'Thanh toán đang được xử lý. Token sẽ được cộng khi xác nhận xong.',
    credited: 'token đã được cộng vào ví của bạn.',
    back: 'Về trang chính',
  },
};

// The IPN is the authoritative credit source, so the result page polls the order
// status for a short while rather than trusting the redirect's status param.
export default function BillingResultPage() {
  const { lang, theme } = useApp();
  const t = T[lang] || T.vi;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const ref = params.get('ref') || '';
  const redirectStatus = params.get('status') || '';

  const [state, setState] = useState('processing'); // processing|success|failed|pending
  const [tokenAmount, setTokenAmount] = useState(0);

  const poll = useCallback(async () => {
    if (!ref) {
      setState(redirectStatus === 'success' ? 'success' : 'failed');
      return;
    }
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      try {
        const res = await billingGetTransactionStatus(ref);
        if (res.status === 'succeeded') {
          setTokenAmount(res.token_amount || 0);
          setState('success');
          return;
        }
        if (['failed', 'expired', 'cancelled'].includes(res.status)) {
          setState('failed');
          return;
        }
      } catch {
        // ignore transient errors and keep polling
      }
      if (attempts >= 8) {
        setState('pending');
        return;
      }
      setTimeout(tick, 2000);
    };
    tick();
  }, [ref, redirectStatus]);

  useEffect(() => {
    poll();
  }, [poll]);

  const dark = theme === 'dark';
  const wrap = dark ? 'bg-slate-900 text-slate-100' : 'bg-slate-50 text-slate-800';
  const card = dark ? 'bg-slate-800 border-slate-700' : 'bg-white border-slate-200';

  return (
    <div className={`min-h-screen flex flex-col ${wrap}`}>
      <div className="flex-1 flex items-center justify-center p-4">
      <div className={`max-w-md w-full rounded-2xl border p-8 text-center shadow-lg ${card}`}>
        {state === 'processing' && (
          <>
            <Loader2 className="mx-auto mb-4 h-12 w-12 animate-spin text-indigo-500" />
            <p className="text-lg font-medium">{t.processing}</p>
          </>
        )}
        {state === 'success' && (
          <>
            <CheckCircle className="mx-auto mb-4 h-12 w-12 text-emerald-500" />
            <h2 className="text-xl font-bold">{t.success}</h2>
            {tokenAmount > 0 && (
              <p className="mt-2 text-sm opacity-80">
                +{tokenAmount} {t.credited}
              </p>
            )}
          </>
        )}
        {state === 'pending' && (
          <>
            <Loader2 className="mx-auto mb-4 h-12 w-12 text-amber-500" />
            <p className="text-base font-medium">{t.pending}</p>
          </>
        )}
        {state === 'failed' && (
          <>
            <XCircle className="mx-auto mb-4 h-12 w-12 text-rose-500" />
            <h2 className="text-xl font-bold">{t.failed}</h2>
          </>
        )}
        <button
          onClick={() => navigate('/app')}
          className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 text-white hover:bg-indigo-700"
        >
          {t.back}
        </button>
      </div>
      </div>
      <SiteFooter />
    </div>
  );
}
