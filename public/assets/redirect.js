(() => {
  fetch('/redirects.json').then(response => response.json()).then(map => {
    let path;
    try { path = decodeURIComponent(location.pathname); } catch { return; }
    const target = map[path] || map[path.replace(/\/?$/, '/')];
    if (target?.startsWith('/') && !target.startsWith('//')) location.replace(target + location.search + location.hash);
  }).catch(() => {});
})();
