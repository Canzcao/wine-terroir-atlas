/* 待共建清单（community 页第三视图）
   数据由 scripts/build-co-build-board.py 生成，每轮采集收束后刷新 public/co-build-data.json
   这里只负责读 JSON + 渲染，不写任何数据。 */
(function () {
  'use strict';

  var DATA_URL = '/co-build-data.json';
  var PER_PAGE = 50;
  var data = null;
  var loading = false;

  var state = {
    tab: 'gaps',        // gaps | have | todo
    kind: 'all',        // all | region | winery
    prio: 'all',
    miss: 'all',
    group: 'all',
    country: 'all',
    q: '',
    page: 1,
  };

  // ---------- 小工具 ----------
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(n) { return (n || 0).toLocaleString('zh-CN'); }
  function el(html) {
    var d = document.createElement('div');
    d.innerHTML = html.trim();
    return d.firstElementChild;
  }

  // ---------- 数据 ----------
  function load() {
    if (data || loading) return Promise.resolve(data);
    loading = true;
    return fetch(DATA_URL, { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('看板数据加载失败（HTTP ' + r.status + '）');
        return r.json();
      })
      .then(function (j) { data = j; loading = false; return j; })
      .catch(function (e) { loading = false; throw e; });
  }

  // ---------- 行展开 ----------
  function regionRows() {
    var cols = data.columns.region;
    return data.regionGaps.map(function (r) {
      var o = {};
      cols.forEach(function (c, i) { o[c] = r[i]; });
      o._kind = 'region';
      return o;
    });
  }
  function wineryRows() {
    var cols = data.columns.winery;
    return data.wineryGaps.map(function (r) {
      var o = {};
      cols.forEach(function (c, i) { o[c] = r[i]; });
      o._kind = 'winery';
      return o;
    });
  }

  // ---------- 筛选 ----------
  function filtered() {
    var rows = [];
    if (state.kind !== 'winery') rows = rows.concat(regionRows());
    if (state.kind !== 'region') rows = rows.concat(wineryRows());
    var q = state.q.trim().toLowerCase();
    return rows.filter(function (r) {
      if (state.prio !== 'all' && r.priority !== state.prio) return false;
      if (state.miss !== 'all' && (r.missing || []).indexOf(state.miss) < 0) return false;
      if (state.group !== 'all' && (r.group || '') !== state.group) return false;
      if (state.country !== 'all' && r.country !== state.country) return false;
      if (q) {
        var hay = [r.name, r.country, r.region, r.website, r.email].join(' ').toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    }).sort(function (a, b) {
      var pr = { P0: 0, P1: 1, P2: 2, P3: 3 };
      if (pr[a.priority] !== pr[b.priority]) return pr[a.priority] - pr[b.priority];
      if (a._kind !== b._kind) return a._kind === 'region' ? -1 : 1;
      if (b.missing.length !== a.missing.length) return b.missing.length - a.missing.length;
      return String(a.name).localeCompare(String(b.name), 'zh');
    });
  }

  // ---------- 渲染 ----------
  function statCards() {
    var t = data.totals;
    var cards = [
      ['已收录记录', num(t.records), ''],
      ['产区', num(t.region), '有坐标 ' + num(t.regionsWithCoord)],
      ['酒庄', num(t.winery), '有坐标 ' + num(t.wineriesWithCoord)],
      ['酒款', num(t.wine), ''],
      ['图片', num(t.photos), ''],
      ['待补项', num(t.needWork), '需补充明细'],
      ['未采集产区', num(t.pendingRegions), 'todo ' + num(data.todoCount)],
      ['候选产区', num(t.candidateRegions), '尚未开做'],
    ];
    return '<section class="cob-stats">' + cards.map(function (c) {
      return '<div class="cob-stat"><b>' + esc(c[1]) + '</b><span>' + esc(c[0]) + '</span>' +
        (c[2] ? '<em>' + esc(c[2]) + '</em>' : '') + '</div>';
    }).join('') + '</section>';
  }

  function filterBar() {
    if (state.tab !== 'gaps') return '';
    var mo = data.missingTotals || {};
    var ro = data.regionMissingTotals || {};
    var allMiss = Object.keys(mo).concat(Object.keys(ro)).filter(function (v, i, a) { return a.indexOf(v) === i; });
    allMiss.sort(function (a, b) { return (mo[b] || 0) + (ro[b] || 0) - ((mo[a] || 0) + (ro[a] || 0)); });
    var countries = data.collected.map(function (c) { return c.country; });
    var groups = Object.keys(data.groupTotals || {});
    var h = '<div class="cob-filters">';
    h += '<label>类型<select data-f="kind"><option value="all">全部</option><option value="region"' +
      (state.kind === 'region' ? ' selected' : '') + '>产区（' + data.regionGaps.length + '）</option>' +
      '<option value="winery"' + (state.kind === 'winery' ? ' selected' : '') + '>酒庄（' + data.wineryGaps.length + '）</option></select></label>';
    h += '<label>优先级<select data-f="prio"><option value="all">全部</option>';
    ['P0', 'P1', 'P2', 'P3'].forEach(function (p) {
      h += '<option value="' + p + '"' + (state.prio === p ? ' selected' : '') + '>' + p + '（' + ((data.priorityTotals || {})[p] || 0) + '）</option>';
    });
    h += '</select></label>';
    h += '<label>缺失项<select data-f="miss"><option value="all">全部</option>' + allMiss.map(function (m) {
      return '<option value="' + esc(m) + '"' + (state.miss === m ? ' selected' : '') + '>' + esc(m) + '（' + ((mo[m] || 0) + (ro[m] || 0)) + '）</option>';
    }).join('') + '</select></label>';
    h += '<label>分组<select data-f="group"><option value="all">全部</option>' + groups.map(function (g) {
      return '<option value="' + esc(g) + '"' + (state.group === g ? ' selected' : '') + '>' + esc(g) + '（' + data.groupTotals[g] + '）</option>';
    }).join('') + '</select></label>';
    h += '<label>国家<select data-f="country"><option value="all">全部</option>' + countries.map(function (c) {
      return '<option value="' + esc(c) + '"' + (state.country === c ? ' selected' : '') + '>' + esc(c) + '</option>';
    }).join('') + '</select></label>';
    h += '<label class="cob-search">搜索<input type="search" data-f="q" placeholder="酒庄名 / 产区 / 官网" value="' + esc(state.q) + '"></label>';
    h += '<button class="cob-reset" data-act="reset">重置</button>';
    h += '<button class="cob-export" data-act="csv">导出 CSV</button>';
    h += '</div>';
    return h;
  }

  function gapsTable() {
    var rows = filtered();
    var pages = Math.max(1, Math.ceil(rows.length / PER_PAGE));
    if (state.page > pages) state.page = pages;
    var slice = rows.slice((state.page - 1) * PER_PAGE, state.page * PER_PAGE);
    var h = '';
    h += '<p class="cob-count">筛选出 <b>' + num(rows.length) + '</b> 项' +
      (rows.length ? '（第 ' + state.page + '/' + pages + ' 页）' : '') + '</p>';
    h += '<div class="cob-table-wrap"><table class="cob-table"><thead><tr>' +
      '<th>优先级</th><th>类型</th><th>国家</th><th>产区</th><th>名称</th>' +
      '<th>缺什么</th><th>缺几项</th><th>酒款</th><th>图片</th><th>可联系</th>' +
      '</tr></thead><tbody>';
    if (!slice.length) {
      h += '<tr><td colspan="10" class="cob-empty">没有匹配的条目，换个筛选条件试试。</td></tr>';
    }
    slice.forEach(function (r) {
      var link = r.website || r.email || '';
      h += '<tr class="cob-p' + r.priority + '">' +
        '<td data-l="优先级"><span class="cob-pill cob-pill-' + r.priority + '">' + r.priority + '</span></td>' +
        '<td data-l="类型">' + (r._kind === 'region' ? '产区' : '酒庄') + '</td>' +
        '<td data-l="国家">' + esc(r.country) + '</td>' +
        '<td data-l="产区">' + esc(r._kind === 'region' ? r.name : r.region) + '</td>' +
        '<td data-l="名称" class="cob-name">' + esc(r.name) + '</td>' +
        '<td data-l="缺什么">' + (r.missing || []).map(function (m) {
          return '<span class="cob-tag">' + esc(m) + '</span>';
        }).join('') + '</td>' +
        '<td data-l="缺几项">' + r.missing.length + '</td>' +
        '<td data-l="酒款">' + (r.wines || 0) + '</td>' +
        '<td data-l="图片">' + (r._kind === 'region' ? (r.photos || 0) : (r.images || 0)) + '</td>' +
        '<td data-l="可联系">' + (link ? '<a href="' + esc(link) + '" target="_blank" rel="noopener">' +
          esc(String(link).replace(/^https?:\/\//, '').slice(0, 28)) + ' ↗</a>' : '<span class="cob-dim">—</span>') + '</td>' +
        '</tr>';
    });
    h += '</tbody></table></div>';
    if (pages > 1) {
      h += '<div class="cob-pager">' +
        '<button data-act="prev"' + (state.page <= 1 ? ' disabled' : '') + '>← 上一页</button>' +
        '<span>' + state.page + ' / ' + pages + '</span>' +
        '<button data-act="next"' + (state.page >= pages ? ' disabled' : '') + '>下一页 →</button>' +
        '</div>';
    }
    return h;
  }

  function haveTable() {
    var rows = data.collected.slice().sort(function (a, b) { return b.wineries - a.wineries; });
    return '<p class="cob-count">共 <b>' + rows.length + '</b> 个国家已在库。「已收集」指的是有实体记录，不代表字段完整 —— 字段缺口看「需补充」。</p>' +
      '<div class="cob-table-wrap"><table class="cob-table"><thead><tr>' +
      '<th>国家</th><th>产区</th><th>产区有坐标</th><th>酒庄</th><th>酒庄有坐标</th><th>酒款</th><th>图片</th><th>完整度</th>' +
      '</tr></thead><tbody>' + rows.map(function (c) {
        var pct = c.wineries ? Math.round(c.wineriesWithCoord / c.wineries * 100) : 0;
        return '<tr>' +
          '<td data-l="国家" class="cob-name">' + esc(c.country) + '</td>' +
          '<td data-l="产区">' + num(c.regions) + '</td>' +
          '<td data-l="产区有坐标">' + num(c.regionsWithCoord) + ' / ' + num(c.regions) + '</td>' +
          '<td data-l="酒庄">' + num(c.wineries) + '</td>' +
          '<td data-l="酒庄有坐标">' + num(c.wineriesWithCoord) + ' / ' + num(c.wineries) + '</td>' +
          '<td data-l="酒款">' + num(c.wines) + '</td>' +
          '<td data-l="图片">' + num(c.photos) + '</td>' +
          '<td data-l="完整度"><span class="cob-bar" title="有坐标酒庄占比"><i style="width:' + pct + '%"></i></span> ' + pct + '%</td>' +
          '</tr>';
      }).join('') + '</tbody></table></div>';
  }

  function todoTable() {
    var qs = data.queueRounds || [];
    var cands = data.candidates || [];
    var empty = data.emptyRegions || [];
    var pend = data.pendingRegions || [];
    var h = '<p class="cob-count">队列里还有 <b>' + pend.length + '</b> 个产区没做完（todo ' + data.todoCount + '），另有 <b>' + cands.length + '</b> 个候选产区尚未开。</p>';

    h += '<h3 class="cob-h3">19 国轮转队列（下一轮按此顺序）</h3>';
    h += '<div class="cob-table-wrap"><table class="cob-table"><thead><tr>' +
      '<th>顺序</th><th>国家</th><th>本次待做产区</th><th>候选产区</th><th>检索语言</th>' +
      '</tr></thead><tbody>' + qs.map(function (q, i) {
        return '<tr>' +
          '<td data-l="顺序">' + (i + 1) + '</td>' +
          '<td data-l="国家" class="cob-name">' + esc(q.country) + ' <small>' + esc(q.code) + '</small></td>' +
          '<td data-l="待做产区">' + (q.todoRegions.length ? q.todoRegions.map(function (n) {
            return '<span class="cob-tag">' + esc(n) + '</span>';
          }).join('') : '<span class="cob-dim">—</span>') + '</td>' +
          '<td data-l="候选产区">' + num(q.candidates) + '</td>' +
          '<td data-l="检索语言">' + (q.languages || []).join(' + ') + '</td>' +
          '</tr>';
      }).join('') + '</tbody></table></div>';

    if (pend.length) {
      h += '<h3 class="cob-h3">待做产区明细（含已侦察未开做）</h3>';
      h += '<div class="cob-table-wrap"><table class="cob-table"><thead><tr>' +
        '<th>国家</th><th>产区</th><th>状态</th><th>备注 / 入口</th></tr></thead><tbody>' +
        pend.map(function (p) {
          return '<tr><td data-l="国家">' + esc(p.country) + '</td>' +
            '<td data-l="产区" class="cob-name">' + esc(p.name) + '</td>' +
            '<td data-l="状态"><span class="cob-pill cob-pill-' + (p.status === 'todo' ? 'P1' : 'P2') + '">' + esc(p.status) + '</span></td>' +
            '<td data-l="备注">' + esc(p.note || '—') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if (cands.length) {
      h += '<h3 class="cob-h3">候选产区（尚未开）</h3>';
      h += '<div class="cob-table-wrap"><table class="cob-table"><thead><tr>' +
        '<th>国家</th><th>产区</th><th>备注</th></tr></thead><tbody>' +
        cands.map(function (c) {
          return '<tr><td data-l="国家">' + esc(c.country) + '</td>' +
            '<td data-l="产区" class="cob-name">' + esc(c.name) + '</td>' +
            '<td data-l="备注">' + esc(c.note || '—') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if (empty.length) {
      h += '<h3 class="cob-h3">库里 0 家酒庄的产区</h3>';
      h += '<ul class="cob-list">' + empty.map(function (e) {
        return '<li><b>' + esc(e[1]) + '</b> · ' + esc(e[2]) + '</li>';
      }).join('') + '</ul>';
    }
    return h;
  }

  function body() {
    if (state.tab === 'have') return haveTable();
    if (state.tab === 'todo') return todoTable();
    return filterBar() + gapsTable();
  }

  function shell() {
    var tabs = [
      ['gaps', '需补充', data.totals.needWork],
      ['have', '已收集', data.collected.length],
      ['todo', '未收集', data.totals.pendingRegions],
    ];
    return '<div class="cob" data-no-i18n>' +
      '<header class="cob-head">' +
      '<div><p class="cob-eyebrow">CO-BUILD BACKLOG</p><h2>待共建清单</h2></div>' +
      '<p class="cob-lede">资料库里<strong>已收集 / 需补充 / 未收集</strong>三块的完整清单。' +
      '每轮产区采集收束后自动刷新；数字与明细口径见 <code>data/catalog-seed.json</code>。</p>' +
      '<p class="cob-meta">生成时间 <b>' + esc(data.generatedDisplay) + '</b>' +
      (data.progress && data.progress.phase ? ' · 采集线当前：' + esc(data.progress.phase) : '') +
      ' · 明细可导出 CSV</p>' +
      '</header>' +
      statCards() +
      '<nav class="cob-tabs">' + tabs.map(function (t) {
        return '<button data-tab="' + t[0] + '"' + (state.tab === t[0] ? ' class="active"' : '') + '>' +
          esc(t[1]) + '<span>' + num(t[2]) + '</span></button>';
      }).join('') + '</nav>' +
      '<div class="cob-body">' + body() + '</div>' +
      '</div>';
  }

  function bind(root) {
    root.querySelectorAll('[data-tab]').forEach(function (b) {
      b.onclick = function () { state.tab = b.dataset.tab; state.page = 1; render(root); };
    });
    root.querySelectorAll('[data-f]').forEach(function (s) {
      var f = s.dataset.f;
      var ev = f === 'q' ? 'input' : 'change';
      s.addEventListener(ev, function () {
        state[f] = s.value;
        state.page = 1;
        if (f !== 'q') render(root);
        else {
          clearTimeout(s._t);
          s._t = setTimeout(function () {
            var focusBack = root.querySelector('[data-f="q"]');
            render(root);
            var again = root.querySelector('[data-f="q"]');
            if (again && focusBack) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
          }, 260);
        }
      });
    });
    root.querySelectorAll('[data-act]').forEach(function (b) {
      b.onclick = function () {
        var act = b.dataset.act;
        if (act === 'reset') {
          state.kind = 'all'; state.prio = 'all'; state.miss = 'all';
          state.group = 'all'; state.country = 'all'; state.q = ''; state.page = 1;
          render(root);
        } else if (act === 'prev') { state.page--; render(root); }
        else if (act === 'next') { state.page++; render(root); }
        else if (act === 'csv') { exportCsv(); }
      };
    });
  }

  function exportCsv() {
    var rows = filtered();
    var head = ['优先级', '类型', '国家', '产区', '名称', '缺失项', '缺几项', '分组', '酒款', '图片', '官网', '邮箱', '记录ID'];
    var lines = [head.join(',')];
    rows.forEach(function (r) {
      lines.push([r.priority, r._kind === 'region' ? '产区' : '酒庄', r.country,
        r._kind === 'region' ? r.name : r.region, r.name, (r.missing || []).join('、'),
        r.missing.length, r.group || '', r.wines || 0,
        r._kind === 'region' ? (r.photos || 0) : (r.images || 0),
        r.website || '', r.email || '', r.id].map(function (v) {
          return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
        }).join(','));
    });
    var blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '风土图鉴-待共建清单-' + (data.generatedDate || '') + '.csv';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  function render(root, forced) {
    var host = forced || document.getElementById('content');
    if (!host) return;
    if (!data) {
      host.innerHTML = '<p class="lede">正在载入待共建清单…</p>';
      load().then(function () { render(host); })
        .catch(function (e) {
          host.innerHTML = '<p class="lede">待共建清单加载失败：' + esc(e.message) +
            '<br><small>数据文件由 <code>scripts/build-co-build-board.py</code> 生成，' +
            '若尚未生成请先跑一次该脚本。</small></p>';
        });
      return;
    }
    host.innerHTML = shell();
    bind(host.querySelector('.cob'));
  }

  // community.js 的 view() 会调这个
  window.renderGaps = function () { render(document.getElementById('content')); };
  // 也允许直接 /community?view=gaps 定位
  window.__coBuild = { load: load, render: render, get data() { return data; } };
})();
