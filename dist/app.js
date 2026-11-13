const query = document.querySelector('#seller-query');
const button = document.querySelector('#search-button');
const results = document.querySelector('#results');
const empty = document.querySelector('#empty-state');
const sellerName = document.querySelector('#seller-name');

function runSearch() {
  const value = query.value.trim();
  if (!value) {
    query.focus();
    return;
  }
  button.disabled = true;
  button.innerHTML = '조회 중 <span>…</span>';
  window.setTimeout(() => {
    sellerName.textContent = value.includes('raum') ? '라움컴퍼니' : '조회된 사업자';
    empty.hidden = true;
    results.hidden = false;
    button.disabled = false;
    button.innerHTML = '조회하기 <span>↗</span>';
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 420);
}

button.addEventListener('click', runSearch);
query.addEventListener('keydown', (event) => { if (event.key === 'Enter') runSearch(); });
