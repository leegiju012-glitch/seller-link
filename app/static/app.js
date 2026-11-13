const form = document.querySelector('#form');
const query = document.querySelector('#query');
const button = document.querySelector('#submit');
const message = document.querySelector('#message');
const result = document.querySelector('#result');
const business = document.querySelector('#business');
const marketplaces = document.querySelector('#marketplaces');

const field = (name, value) => `<dt>${name}</dt><dd>${value || '-'}</dd>`;
const escape = (value) => String(value || '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
const label = (status) => ({ found: '입점 확인', not_found: '입점 X', not_checked: '확인 X', error: '확인 X' }[status] || status);

function card(item) {
  const link = item.store_url ? `<a href="${escape(item.store_url)}" target="_blank" rel="noreferrer">${escape(item.store_name || item.store_url)}</a>` : '-';
  return `<article class="card"><h2>${escape(item.platform)}</h2><p><span class="status ${escape(item.status).replace('_', '-')}">${label(item.status)}</span></p><p>${link}</p>${item.evidence ? `<p>${escape(item.evidence)}</p>` : ''}</article>`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  result.hidden = true;
  message.textContent = '조회 중…';
  button.disabled = true;
  try {
    const response = await fetch(`/api/lookup?q=${encodeURIComponent(query.value.trim())}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '조회에 실패했습니다.');
    const info = data.business;
    business.innerHTML = [
      field('상호', escape(info.company_name)),
      field('대표자', escape(info.representative_name)),
      field('사업자번호', escape(info.business_number)),
      field('운영상태', escape(info.operating_status)),
      field('통신판매번호', escape(info.mail_order_number)),
    ].join('');
    marketplaces.innerHTML = data.marketplaces.map(card).join('');
    message.textContent = data.warnings.join(' ');
    result.hidden = false;
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
