// Build a clean, self-contained printable report for one analysis and open the
// browser's print dialog (the user picks "Save as PDF").
//
// Why print-to-PDF instead of jsPDF: this renders through the browser using
// system fonts, so Vietnamese diacritics are never mangled (no TTF embedding),
// and the charts are re-drawn as plain HTML bars (jsPDF cannot rasterise the
// recharts SVG reliably). Zero extra dependencies.

const TXT = {
    en: {
        report: 'Architecture Style Analysis Report',
        generated: 'Generated',
        sourceImage: 'Source image',
        style: 'Architectural style',
        confidence: 'Confidence',
        flags: 'Flags',
        uncertain: 'Uncertain',
        hybrid: 'Hybrid / eclectic',
        panelAgreement: 'Panel agreement',
        description: 'Description',
        composition: 'Composition explanation',
        keyEvidence: 'Key evidence',
        distribution: 'Style distribution',
        perStyle: 'Why each style',
        evidence: 'Evidence (12 dimensions)',
        dimension: 'Dimension',
        feature: 'Feature',
        suggests: 'Suggests',
        note: 'Note',
        primary: 'Primary',
        secondary: 'Secondary',
        footer: 'ArchiAI — Open-Vocabulary Architecture Recognition'
    },
    vi: {
        report: 'Báo cáo phân tích phong cách kiến trúc',
        generated: 'Tạo lúc',
        sourceImage: 'Ảnh gốc',
        style: 'Phong cách kiến trúc',
        confidence: 'Độ tin cậy',
        flags: 'Cờ',
        uncertain: 'Chưa chắc chắn',
        hybrid: 'Lai / pha trộn',
        panelAgreement: 'Đồng thuận hội đồng',
        description: 'Mô tả',
        composition: 'Giải thích tổ hợp',
        keyEvidence: 'Bằng chứng chính',
        distribution: 'Phân bố phong cách',
        perStyle: 'Vì sao mỗi phong cách',
        evidence: 'Bằng chứng (12 chiều)',
        dimension: 'Chiều',
        feature: 'Đặc trưng',
        suggests: 'Gợi ý',
        note: 'Ghi chú',
        primary: 'Chính',
        secondary: 'Phụ',
        footer: 'ArchiAI — Nhận dạng phong cách kiến trúc mở'
    }
};

function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function pick(result, viField, enField, useVi) {
    return (useVi && result[viField]) || result[enField];
}

/**
 * Open a printable report for the given analysis result.
 *
 * @param {object} result   Full AnalyzeResponse (as shown on screen).
 * @param {string|null} imageUrl  Object URL of the source image (optional).
 * @param {'en'|'vi'} lang  Report language; picks the *_vi fields when 'vi'.
 */
export function exportAnalysisPdf(result, imageUrl, lang = 'en') {
    if (!result) return;
    const t = TXT[lang] || TXT.en;
    const useVi = lang === 'vi';

    const explanation = pick(result, 'explanation_vi', 'explanation', useVi);
    const composition = pick(result, 'composition_explanation_vi', 'composition_explanation', useVi);
    const keyEvidence = pick(result, 'key_evidence_vi', 'key_evidence', useVi) || [];
    const perStyleEvidence = pick(result, 'evidence_per_style_vi', 'evidence_per_style', useVi) || {};
    const sheet = (useVi && result.evidence_sheet_vi) || result.evidence_sheet;

    const dist = result.style_distribution?.distribution || {};
    const primary = result.style_distribution?.primary;
    const distRows = Object.entries(dist)
        .map(([s, p]) => ({ style: s, pct: Math.round(p * 100) }))
        .filter((d) => d.pct > 0)
        .sort((a, b) => b.pct - a.pct);

    const badges = [];
    if (result.uncertain) badges.push(t.uncertain);
    if (result.hybrid) badges.push(t.hybrid);
    if (typeof result.panel_agreement === 'number') {
        badges.push(`${t.panelAgreement}: ${(result.panel_agreement * 100).toFixed(0)}%`);
    }

    const distHtml = distRows.length ? `
        <h2>${esc(t.distribution)}</h2>
        <div class="bars">
            ${distRows.map((d) => `
                <div class="bar-row">
                    <span class="bar-label">${esc(d.style)}</span>
                    <span class="bar-track"><span class="bar-fill" style="width:${d.pct}%"></span></span>
                    <span class="bar-pct">${d.pct}%</span>
                </div>`).join('')}
        </div>` : '';

    const perStyleHtml = Object.keys(perStyleEvidence).length ? `
        <h2>${esc(t.perStyle)}</h2>
        ${Object.entries(perStyleEvidence).map(([style, bullets]) => `
            <div class="style-block">
                <div class="style-head">${esc(style)} ${style === primary ? `<em>(${esc(t.primary)})</em>` : `<em>(${esc(t.secondary)})</em>`}</div>
                <ul>${(bullets || []).map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
            </div>`).join('')}` : '';

    const evidenceHtml = sheet?.items?.length ? `
        <h2>${esc(t.evidence)}</h2>
        <table>
            <thead><tr>
                <th>${esc(t.dimension)}</th><th>${esc(t.feature)}</th>
                <th>${esc(t.suggests)}</th><th>${esc(t.note)}</th>
            </tr></thead>
            <tbody>
                ${sheet.items.map((it) => `<tr>
                    <td>${esc(it.dimension)}</td>
                    <td>${esc(it.feature)}</td>
                    <td>${esc((it.suggested_styles || []).join(', '))}</td>
                    <td>${esc(it.note)}</td>
                </tr>`).join('')}
            </tbody>
        </table>` : '';

    const keyEvidenceHtml = keyEvidence.length ? `
        <h2>${esc(t.keyEvidence)}</h2>
        <ul>${keyEvidence.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>` : '';

    const html = `<!DOCTYPE html>
<html lang="${lang}">
<head>
<meta charset="utf-8" />
<title>${esc(t.report)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', Roboto, Arial, sans-serif; color: #1e293b; margin: 32px; line-height: 1.5; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 15px; margin: 22px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #00d2ff; color: #0f172a; }
  .meta { color: #64748b; font-size: 12px; margin-bottom: 18px; }
  .verdict { display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }
  .verdict .style-name { font-size: 26px; font-weight: 800; color: #0f172a; }
  .kv { font-size: 13px; margin: 4px 0; }
  .kv b { color: #0f172a; }
  .badges span { display: inline-block; background: #eef2ff; border: 1px solid #c7d2fe; color: #4338ca; padding: 2px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; margin: 2px 4px 2px 0; }
  img.src { max-width: 280px; max-height: 220px; border-radius: 10px; border: 1px solid #e2e8f0; object-fit: contain; }
  ul { margin: 6px 0; padding-left: 20px; }
  li { font-size: 13px; margin: 2px 0; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { border: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #f8fafc; font-weight: 700; }
  .bars { font-size: 12px; }
  .bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; }
  .bar-label { width: 160px; font-weight: 600; }
  .bar-track { flex: 1; height: 9px; background: #e2e8f0; border-radius: 999px; overflow: hidden; }
  .bar-fill { display: block; height: 100%; background: linear-gradient(90deg,#00d2ff,#9d50bb); }
  .bar-pct { width: 42px; text-align: right; font-weight: 700; color: #0369a1; }
  .style-block { margin-bottom: 10px; }
  .style-head { font-weight: 700; color: #0f172a; }
  .style-head em { color: #7c3aed; font-style: normal; font-size: 11px; }
  blockquote { border-left: 3px solid #9d50bb; margin: 6px 0; padding-left: 12px; color: #334155; font-style: italic; }
  footer { margin-top: 28px; padding-top: 10px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 11px; }
  @media print { body { margin: 16mm; } h2 { page-break-after: avoid; } table, .style-block { page-break-inside: avoid; } }
</style>
</head>
<body>
  <h1>${esc(t.report)}</h1>
  <div class="meta">${esc(t.generated)}: ${esc(new Date().toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US'))}</div>

  <div class="verdict">
    ${imageUrl ? `<img class="src" src="${esc(imageUrl)}" alt="" />` : ''}
    <div>
      <div class="kv"><b>${esc(t.style)}</b></div>
      <div class="style-name">${esc(result.style)}</div>
      <div class="kv"><b>${esc(t.confidence)}:</b> ${(result.confidence * 100).toFixed(0)}%</div>
      ${badges.length ? `<div class="badges">${badges.map((b) => `<span>${esc(b)}</span>`).join('')}</div>` : ''}
    </div>
  </div>

  ${explanation ? `<h2>${esc(t.description)}</h2><blockquote>${esc(explanation)}</blockquote>` : ''}
  ${composition && composition !== explanation ? `<h2>${esc(t.composition)}</h2><p>${esc(composition)}</p>` : ''}
  ${keyEvidenceHtml}
  ${distHtml}
  ${perStyleHtml}
  ${evidenceHtml}

  <footer>${esc(t.footer)}</footer>
  <script>
    window.onload = function () { window.focus(); window.print(); };
  </script>
</body>
</html>`;

    const win = window.open('', '_blank');
    if (!win) return; // popup blocked
    win.document.open();
    win.document.write(html);
    win.document.close();
}
