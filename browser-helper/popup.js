const API_URL = 'https://seller-link.onrender.com/api/extension-lookup';
const analyze = document.querySelector('#analyze');
const message = document.querySelector('#message');
const result = document.querySelector('#result');
const sellerTabs = document.querySelector('#seller-tabs');
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
    const text = document.body.innerText || '';
    const candidates = [];
    for (const match of text.matchAll(/(?<!\d)(\d{3}[-\s]?\d{2}[-\s]?\d{5})(?!\d)/g)) {
      const number = match[1].replace(/\D/g, '');
      if (!validBusinessNumber(number)) continue;
      const nearby = text.slice(Math.max(0, match.index - 180), match.index + match[0].length + 180).toLowerCase();
      if (nearby.includes('네이버㈜') || nearby.includes('naver corp') || nearby.includes('대표이사')) continue;
      const score = ['사업자', 'business', 'brno', '사업자등록'].filter((token) => nearby.includes(token)).length;
      candidates.push({ number, score });
    }
    candidates.sort((a, b) => b.score - a.score);
    const phones = [...text.matchAll(/(?<!\d)(?:0\d{1,2}[-\s]?)?\d{3,4}[-\s]?\d{4}(?!\d)/g)]
      .map((match) => match[0].replace(/\D/g, ''))
      .filter((phone) => /^0\d{8,10}$/.test(phone));
    const emails = [...text.matchAll(/(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.+-])/g)]
      .map((match) => match[0].toLowerCase());
    const companyMatch = text.match(/상호명\s*\n?\s*([^\n]+)/);
    return {
      source_url: location.href,
      business_number: candidates[0]?.number,
      confidence: candidates[0]?.score || 0,
      requires_verification: /인증\s*절차\s*이후\s*확인/.test(text),
      company_name: companyMatch?.[1]?.trim() || null,
      phones: [...new Set(phones)].slice(0, 10),
      emails: [...new Set(emails)].slice(0, 10)
    };
  };

  const sellerInfoControl = [...document.querySelectorAll('button, a, [role="button"]')]
    .find((element) => /판매자\s*정보|사업자\s*정보|사업자등록\s*정보/.test(element.textContent || ''));
  if (sellerInfoControl) {
    sellerInfoControl.click();
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  return collect();
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

function sourceSmartStoreUrl(currentUrl) {
  try {
    const current = new URL(currentUrl);
    if (current.hostname === 'smartstore.naver.com') return current.href;
    if (
      current.hostname === 'shopping.naver.com' &&
      current.pathname.startsWith('/popup/seller-info/')
    ) {
      const previous = current.searchParams.get('prevUrl');
      if (previous && new URL(previous).hostname === 'smartstore.naver.com') return previous;
    }
  } catch (_) {
    return null;
  }
  return null;
}

async function analyzeSellerPopup(tab) {
  analyze.disabled = true;
  result.hidden = true;
  sellerTabs.hidden = true;
  message.textContent = '공개 판매자 정보 확인 중…';
  try {
    if (!tab?.id) {
      throw new Error('판매자 정보 창을 찾지 못했습니다.');
    }
    const sourceUrl = tab.url ? sourceSmartStoreUrl(tab.url) : null;
    if (!sourceUrl) {
      throw new Error('스마트스토어와 연결된 판매자 정보 창이 아닙니다.');
    }
    const frames = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: extractPublicIdentifiers
    });
    const identifiers = frames
      .map((frame) => frame.result)
      .filter((value) => value?.business_number)
      .sort((left, right) => right.confidence - left.confidence)[0];
    if (!identifiers?.business_number) {
      if (frames.some((frame) => frame.result?.requires_verification)) {
        throw new Error('네이버가 판매자 상세정보를 인증 뒤에만 보여줍니다. 페이지의 상세정보 확인에서 직접 인증한 뒤 다시 실행하세요.');
      }
      throw new Error('현재 페이지의 공개 판매자 정보에서 사업자등록번호를 찾지 못했습니다.');
    }
    identifiers.source_url = sourceUrl;
    delete identifiers.confidence;
    delete identifiers.requires_verification;
    delete identifiers.company_name;
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
}

analyze.addEventListener('click', async () => {
  result.hidden = true;
  sellerTabs.hidden = true;
  message.textContent = '열린 판매자 정보 창 확인 중…';
  try {
    const tabs = await chrome.tabs.query({
      url: ['https://shopping.naver.com/popup/seller-info/*']
    });
    const candidates = tabs
      .map((tab) => ({ tab, sourceUrl: sourceSmartStoreUrl(tab.url || '') }))
      .filter(({ sourceUrl }) => sourceUrl);
    if (!candidates.length) {
      throw new Error('인증 완료된 판매자 정보 창을 먼저 열어주세요.');
    }
    sellerTabs.innerHTML = candidates.map(({ tab, sourceUrl }) => {
      const storeId = new URL(sourceUrl).pathname.split('/').filter(Boolean)[0] || '스토어';
      return `<button class="seller-tab" type="button" data-tab-id="${escape(tab.id)}"><strong>${escape(storeId)}</strong><small>이 판매자 정보 분석</small></button>`;
    }).join('');
    sellerTabs.hidden = false;
    message.textContent = '분석할 판매자 정보 창을 선택하세요.';
  } catch (error) {
    message.textContent = error.message || '판매자 정보 창을 찾지 못했습니다.';
  }
});

sellerTabs.addEventListener('click', (event) => {
  const button = event.target.closest('[data-tab-id]');
  if (!button) return;
  chrome.tabs.get(Number(button.dataset.tabId)).then(analyzeSellerPopup);
});
