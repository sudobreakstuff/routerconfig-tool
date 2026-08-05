/* RouterConfig Pro site — hero packet canvas, event ticker, counters, reveal. */

(function () {
  "use strict";

  /* ------------------------------------------------------------ ticker */
  var TICKERS = [
    ["CPE-0417", "Ubiquiti", "config applied", "ok"],
    ["CPE-1023", "MikroTik", "deployed to ISP", "ok"],
    ["CPE-0839", "TP-Link", "firmware upgrade", "ok"],
    ["CPE-0056", "Ubiquiti", "tunnel open", "ok"],
    ["CPE-0911", "MikroTik", "config applied", "ok"],
    ["CPE-0342", "Generic", "restore config", "err"],
    ["CPE-0770", "TP-Link", "deployed to ISP", "ok"],
    ["CPE-1184", "Ubiquiti", "reboot sent", "ok"],
    ["CPE-0521", "MikroTik", "config diff OK", "ok"],
    ["CPE-0447", "Ubiquiti", "backup taken", "ok"],
  ];
  var tickerEl = document.getElementById("ticker");
  if (tickerEl) {
    var items = TICKERS.map(function (t) {
      var cls = t[3] === "ok" ? "ok" : "err";
      return '<span class="t-item">' + t[0] + " · <span class=\"vendor\">" + t[1] + "</span> <span class=\"" + cls + "\">" + t[2] + "</span></span>";
    }).join("");
    tickerEl.innerHTML = items + items;
    tickerEl.style.animation = "marquee 48s linear infinite";
    var st = document.createElement("style");
    st.textContent = "@keyframes marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }";
    document.head.appendChild(st);
  }

  /* ------------------------------------------------------------ hero canvas */
  var canvas = document.getElementById("hero-canvas");
  if (canvas) {
    var ctx = canvas.getContext("2d");
    var W, H, nodes = [], edges = [], packets = [];

    function resize() {
      W = canvas.width = canvas.offsetWidth;
      H = canvas.height = canvas.offsetHeight;
      layout();
    }
    resize();
    window.addEventListener("resize", resize);

    function layout() {
      var nx = 7, ny = 4;
      nodes = [];
      for (var i = 0; i < nx; i++) {
        for (var j = 0; j < ny; j++) {
          var x = W * (0.12 + i * (0.76 / (nx - 1)));
          var y = H * (0.16 + j * (0.68 / (ny - 1)));
          x += (Math.random() - 0.5) * 40;
          y += (Math.random() - 0.5) * 34;
          nodes.push({ x: x, y: y, r: j === 0 && i === 3 ? 6 : 3, phase: Math.random() * 6.28 });
        }
      }
      edges = [];
      for (var a = 0; a < nodes.length; a++) {
        for (var b = a + 1; b < nodes.length; b++) {
          var d = Math.hypot(nodes[a].x - nodes[b].x, nodes[a].y - nodes[b].y);
          if (d < 170 && Math.random() < 0.55) edges.push({ a: a, b: b });
        }
      }
      packets = [];
      for (var e = 0; e < edges.length; e++) {
        if (Math.random() < 0.5) packets.push({ e: e, t: Math.random() });
      }
    }

    var t = 0;
    function draw() {
      t += 0.0035;
      ctx.clearRect(0, 0, W, H);
      for (var e = 0; e < edges.length; e++) {
        var ed = edges[e];
        var na = nodes[ed.a], nb = nodes[ed.b];
        ctx.strokeStyle = "rgba(92,106,125,.3)";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(na.x, na.y); ctx.lineTo(nb.x, nb.y); ctx.stroke();
      }
      for (var p = 0; p < packets.length; p++) {
        var pk = packets[p];
        var ed2 = edges[pk.e];
        if (!ed2) continue;
        pk.t += 0.0045;
        if (pk.t > 1) { pk.t = 0; pk.e = Math.floor(Math.random() * edges.length); continue; }
        var a2 = nodes[ed2.a], b2 = nodes[ed2.b];
        var x = a2.x + (b2.x - a2.x) * pk.t;
        var y = a2.y + (b2.y - a2.y) * pk.t;
        ctx.fillStyle = "#46d160";
        ctx.shadowColor = "#46d160"; ctx.shadowBlur = 8;
        ctx.beginPath(); ctx.arc(x, y, 2, 0, 6.28); ctx.fill();
        ctx.shadowBlur = 0;
      }
      for (var n = 0; n < nodes.length; n++) {
        var nd = nodes[n];
        var pulse = 0.5 + 0.5 * Math.sin(t * 3 + nd.phase);
        ctx.fillStyle = nd.r > 4 ? "rgba(245,165,36,.95)" : "rgba(245,165,36,.55)";
        ctx.beginPath(); ctx.arc(nd.x, nd.y, nd.r + pulse * 1.6, 0, 6.28); ctx.fill();
      }
      requestAnimationFrame(draw);
    }
    draw();
  }

  /* ------------------------------------------------------------ counters */
  var counted = false;
  function animateCounters() {
    if (counted) return;
    var els = document.querySelectorAll(".hmv");
    if (!els.length) return;
    var rect = els[0].closest(".hero-metrics").getBoundingClientRect();
    if (rect.top > window.innerHeight * 0.95) return;
    counted = true;
    els.forEach(function (el) {
      var target = parseInt(el.dataset.count, 10);
      var suffix = el.dataset.suffix || "";
      var start = null;
      function step(ts) {
        if (!start) start = ts;
        var k = Math.min(1, (ts - start) / 1100);
        el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3))) + suffix;
        if (k < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }
  window.addEventListener("scroll", animateCounters);
  animateCounters();

  /* ------------------------------------------------------------ reveal */
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll(".section, .loop-step, .wsf, .spec-row").forEach(function (el) {
    el.classList.add("reveal");
    io.observe(el);
  });
})();
