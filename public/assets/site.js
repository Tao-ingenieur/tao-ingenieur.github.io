(() => {
  const input = document.querySelector('#search-input');
  const buttons = [...document.querySelectorAll('[data-filter]')];
  const rows = [...document.querySelectorAll('[data-post-id]')];
  const status = document.querySelector('.search-status');
  let category = 'all';
  let index = null;
  let pending = null;
  let renderVersion = 0;
  const normalize = value => value.normalize('NFKC').toLocaleLowerCase();
  async function loadIndex() {
    if (index) return index;
    if (!pending) pending = fetch('/search.json').then(response => {
      if (!response.ok) throw new Error('Search unavailable');
      return response.json();
    }).then(data => index = new Map(data.map(post => [String(post.id), normalize(post.title + ' ' + post.plain)])))
      .catch(error => { pending = null; throw error; });
    return pending;
  }
  async function filter() {
    const version = ++renderVersion;
    const terms = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
    let search = null;
    if (terms.length) {
      try { search = await loadIndex(); }
      catch { status.classList.remove('sr-only'); status.textContent = '全文搜索暂时不可用，当前按标题筛选。'; }
    }
    if (version !== renderVersion) return;
    let count = 0;
    for (const row of rows) {
      const text = search?.get(row.dataset.postId) ?? normalize(row.querySelector('h2').textContent);
      const visible = (category === 'all' || row.dataset.category === category) && terms.every(term => text.includes(term));
      row.hidden = !visible;
      if (visible) count++;
    }
    document.querySelector('.empty-state').hidden = count > 0;
    if (!status.textContent.includes('暂时不可用') || search) {
      status.classList.add('sr-only');
      status.textContent = `找到 ${count} 篇文章`;
    }
    buttons.forEach(button => {
      const active = button.dataset.filter === category;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }
  if (input) {
    document.querySelector('.search').addEventListener('submit', event => { event.preventDefault(); filter(); });
    input.addEventListener('input', filter);
    buttons.forEach(button => button.addEventListener('click', () => { category = button.dataset.filter; filter(); }));
    document.querySelector('#reset-search').addEventListener('click', () => { category = 'all'; input.value = ''; filter(); input.focus(); });
    document.addEventListener('keydown', event => {
      if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !document.activeElement.isContentEditable) {
        event.preventDefault(); input.focus();
      }
      if (event.key === 'Escape' && document.activeElement === input) { input.value = ''; filter(); input.blur(); }
    });
  }
  const article = document.querySelector('[data-article]');
  if (article) {
    const progress = document.querySelector('.reading-progress');
    const update = () => {
      const start = article.getBoundingClientRect().top + scrollY;
      const distance = Math.max(1, article.offsetHeight - innerHeight * 0.6);
      progress.style.width = `${Math.min(100, Math.max(0, (scrollY - start + 180) / distance * 100))}%`;
    };
    addEventListener('scroll', update, { passive: true });
    addEventListener('resize', update); update();
  }
})();
