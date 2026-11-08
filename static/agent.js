/* Ask-the-review panel. Talks to the Lambda function URL in data-agent-url on <body>. */
(function () {
  var url = document.body.getAttribute('data-agent-url');
  if (!url) return;
  var site = document.body.getAttribute('data-site-name') || 'the review';
  var history = [];
  var busy = false;

  var fab = el('button', 'ag-fab', '<span class="ag-label">Ask the review</span><svg class=\"ag-spark\" viewBox=\"0 0 44 44\" aria-hidden=\"true\"><rect x=\"6\" y=\"10\" width=\"30\" height=\"26\" fill=\"#fff\"/><path class=\"in\" d=\"M6 16 H18 A12 12 0 0 1 30 28 V36 H6 Z\" fill=\"#fff\"/><path d=\"M19 6 L22.4 15.6 L32 19 L22.4 22.4 L19 32 L15.6 22.4 L6 19 L15.6 15.6 Z\" fill=\"currentColor\"/><path d=\"M34 24 L35.8 28.2 L40 30 L35.8 31.8 L34 36 L32.2 31.8 L28 30 L32.2 28.2 Z\" fill=\"currentColor\"/></svg>');
  fab.setAttribute('aria-haspopup', 'dialog');
  var panel = el('aside', 'ag-panel');
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Ask the review');
  panel.innerHTML =
    '<div class="ag-head"><div><div class="ag-title">Ask the review</div><div class="ag-sub">Answers come only from the released state of ' + site + '. It can explain the method, find papers, and point you to the right page. It is not the author.</div></div><button class="ag-close" aria-label="Close">×</button></div>' +
    '<div class="ag-log" aria-live="polite"></div>' +
    '<div class="ag-sugg"></div>' +
    '<form class="ag-form"><textarea class="ag-in" rows="2" placeholder="Ask about a research question, a paper, the gap matrix, or how the review works…" aria-label="Your question"></textarea><button class="ag-send" type="submit">Send</button></form>' +
    '<div class="ag-foot">Shared questions are logged anonymously to improve the review; nothing else is stored. Daily usage is capped.</div>';
  // Mount inline at the top-left of the page content: the home page provides #ag-slot (beside the title);
  // other pages get the pill inserted above their first <h1>. Falls back to a floating button.
  var slot = document.getElementById('ag-slot');
  if (!slot) { var h1 = document.querySelector('.page h1, main h1, section h1'); if (h1 && h1.parentElement) { slot = document.createElement('div'); slot.id = 'ag-slot'; h1.parentElement.insertBefore(slot, h1.parentElement.firstChild); } }
  if (slot) { fab.classList.add('inline'); slot.appendChild(fab); } else { document.body.appendChild(fab); }
  document.body.appendChild(panel);

  var log = panel.querySelector('.ag-log'), form = panel.querySelector('.ag-form'),
      input = panel.querySelector('.ag-in'), send = panel.querySelector('.ag-send'), sugg = panel.querySelector('.ag-sugg');

  var suggestions = [
    'What is this review and how does it work?',
    'Which papers should I read first, and why?',
    'Where are the biggest gaps in the literature?',
    'Explain the gap matrix axes.',
    'How is AI used in screening, and how is it audited?'
  ];
  suggestions.forEach(function (q) {
    var b = el('button', 'ag-chip', q); b.type = 'button';
    b.addEventListener('click', function () { input.value = q; form.dispatchEvent(new Event('submit', {cancelable: true})); });
    sugg.appendChild(b);
  });

  function open() { panel.classList.add('on'); fab.setAttribute('aria-expanded', 'true'); if (!slot) fab.classList.add('hide'); setTimeout(function () { input.focus(); }, 50); }
  function close() { panel.classList.remove('on'); fab.setAttribute('aria-expanded', 'false'); fab.classList.remove('hide'); fab.focus(); }
  fab.addEventListener('click', open);
  panel.querySelector('.ag-close').addEventListener('click', close);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && panel.classList.contains('on')) close(); });
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.dispatchEvent(new Event('submit', {cancelable: true})); } });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (!q || busy) return;
    input.value = '';
    sugg.style.display = 'none';
    add('user', q);
    history.push({role: 'user', content: q});
    var thinking = add('bot', '<span class="ag-think">Thinking…</span>');
    busy = true; send.disabled = true;
    fetch(url, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({messages: history.slice(-8)})})
      .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
      .then(function (res) {
        thinking.remove();
        if (!res.ok) { add('bot', '<em>' + esc(res.j.error || 'Something went wrong.') + '</em>'); history.pop(); return; }
        add('bot', md(res.j.reply));
        history.push({role: 'assistant', content: res.j.reply});
      })
      .catch(function () { thinking.remove(); add('bot', '<em>Could not reach the assistant. The review itself is always available.</em>'); history.pop(); })
      .finally(function () { busy = false; send.disabled = false; input.focus(); });
  });

  function add(who, html) {
    var m = el('div', 'ag-msg ' + who); m.innerHTML = html; log.appendChild(m); log.scrollTop = log.scrollHeight; return m;
  }
  function el(tag, cls, html) { var e = document.createElement(tag); e.className = cls; if (html) e.innerHTML = html; return e; }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  // Minimal, safe Markdown: paragraphs, bullets, bold, inline code, [text](url) with http(s) or relative URLs only.
  function md(s) {
    var t = esc(s);
    t = t.replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/)[^)\s]+)\)/g, function (_, a, b) {
      var ext = /^https?:/.test(b) && b.indexOf(location.origin) !== 0;
      return '<a href="' + b + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + '>' + a + '</a>';
    });
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
    var out = [], list = [];
    t.split(/\n/).forEach(function (line) {
      var mm = line.match(/^\s*[-*]\s+(.*)$/);
      if (mm) { list.push('<li>' + mm[1] + '</li>'); return; }
      if (list.length) { out.push('<ul>' + list.join('') + '</ul>'); list = []; }
      if (line.trim()) out.push('<p>' + line + '</p>');
    });
    if (list.length) out.push('<ul>' + list.join('') + '</ul>');
    return out.join('');
  }
})();
