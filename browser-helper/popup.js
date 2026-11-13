const API_URL = 'https://seller-link.onrender.com/api/extension-lookup';
const analyze = document.querySelector('#analyze');
const message = document.querySelector('#message');
const result = document.querySelector('#result');
const business = document.querySelector('#business');
const markets = document.querySelector('#markets');

const escape = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
}[char]));

async function extractPublicIdentifiers() {
  const validBusinessNumber = (value) => {
    const digits = value.replace(/\D/g, '');
    if (!/^\d{10}$/.test(digits)) return false;
    const weights = [1, 3, 7, 1, 3, 7, 1, 3, 5];
    let total = [...digits.slice(0, 9)].reduce((sum, digit, index) => sum + Number(digit) * weights[index], 0);
    total += Math.floor(Number(digits[8]) * 5 / 10);
    return (10 - total % 10) % 10 === Number(digits[9]);
  };
  const collect = () => {
    const html = document.documentElement.innerHTML;
    const text = document.body.innerText || '';
    const candidates = [];
    for (const source of [html, text]) {
      for (const match of source.matchAll(/(?<!\d)(\d{3}[-\s]?\d{2}[-\s]?\d{5})(?!\d)/g)) {
        const number = match[1].replace(/\D/g, '');
        if (!validBusinessNumber(number)) continue;
        const nearby = source.slice(Math.max(0, match.index - 180), match.index + match[0].length + 180).toLowerCase();
        const score = ['사업자', 'business', 'brno', '사업자등록'].filter((token) => nearby.includes(token)).length;
        candidates.push({ number, score });
      }
    }
    candidates.sort((a, b) => b.score - a.score);
    const phones = [...text.matchAll(/(?<!\d)(?:0\d{1,2}[-\s]?)?\d{3,4}[-\s]?\d{4}(?!\d)/g)]
      .map((match) => match[0].replace(/\D/g, ''))
      .filter((phone) => /^0\d{8,10}$/.test(phone));
    const emails = [...text.matchAll(/(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.+-])/g)]
      .map((match) => match[0].toLowerCase());
    return {
      source_url: location.href,
      business_number: candidates[0]?.number,
      phones: [...new Set(phones)].slice(0, 10),
      emails: [...new Set(emails)].slice(0, 10)
    };
  };

  let identifiers = collect();
  if (identifiers.business_number) return identifiers;

  const sellerInfoControl = [...document.querySelectorAll('button, a, [role="button"]')]
    .find((element) => /판매자\s*정보|사업자\s*정보|사업자등록\s*정보/.test(element.textContent || ''));
  if (sellerInfoControl) {
    sellerInfoControl.click();
    await new Promise((resolve) => setTimeout(resolve, 700));
    identifiers = collect();
  }
  return identifiers;
}

function render(data) {
  const info = data.business;
  business.innerHTML = [
    ['상호', info.company_name],
    ['대표자', info.representative_name],
    ['사업자번호', info.business_number]
  ].map(([name, value]) => `<dt>${escape(name)}</dt><dd>${escape(value || '-')}</dd>`).join('');
  markets.innerHTML = data.marketplaces.map((item) => {
    const label = item.status === 'found' ? '입점 확인' : '확인 X';
    const link = item.store_url ? `<a href="${escape(item.store_url)}" target="_blank">${escape(item.store_url)}</a>` : '-';
    return `<article class="market"><strong>${escape(item.platform)} · ${label}</strong><p>${link}</p></article>`;
  }).join('');
  result.hidden = false;
}

analyze.addEventListener('click', async () => {
  analyze.disabled = true;
  result.hidden = true;
  message.textContent = '공개 판매자 정보 확인 중…';
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https:\/\/smartstore\.naver\.com\//.test(tab.url || '')) {
      throw new Error('스마트스토어 페이지를 연 뒤 실행하세요.');
    }
    const [{ result: identifiers }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPublicIdentifiers
    });
    if (!identifiers?.business_number) {
      throw new Error('현재 페이지의 공개 판매자 정보에서 사업자등록번호를 찾지 못했습니다.');
    }
    message.textContent = '연결 판매처 조회 중…';
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(identifiers)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '조회에 실패했습니다.');
    render(data);
    message.textContent = '';
  } catch (error) {
    message.textContent = error.message || '조회에 실패했습니다.';
  } finally {
    analyze.disabled = false;
  }
});
