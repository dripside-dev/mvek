// ===== MVEK SITE — main.js =====

/* ---- Pixel sprite renderer ---- */
const SPRITES = {
  student: [
    // body
    { op:'r', color:'#4cc9f0', x:0, y:0, w:16, h:20 },
    // head
    { op:'r', color:'#f5c842', x:0, y:-18, w:14, h:14 },
    // eyes
    { op:'r', color:'#000', x:-4, y:-16, w:4, h:4 },
    { op:'r', color:'#000', x:2, y:-16, w:4, h:4 },
    // bag
    { op:'r', color:'#2e2e4a', x:10, y:-4, w:8, h:12 },
  ],
  tutor: [
    { op:'r', color:'#9d4edd', x:0, y:0, w:14, h:18 },
    { op:'r', color:'#e8e8f0', x:0, y:-16, w:12, h:12 },
    { op:'r', color:'#000', x:-3, y:-14, w:3, h:3 },
    { op:'r', color:'#000', x:2, y:-14, w:3, h:3 },
    // clipboard
    { op:'r', color:'#c49a1a', x:-14, y:-2, w:8, h:10 },
  ],
  boss: [
    { op:'r', color:'#e63946', x:0, y:0, w:22, h:26 },
    { op:'r', color:'#f5c842', x:0, y:-24, w:20, h:20 },
    { op:'r', color:'#000', x:-5, y:-20, w:5, h:5 },
    { op:'r', color:'#000', x:3, y:-20, w:5, h:5 },
    // tie
    { op:'r', color:'#f5c842', x:0, y:2, w:5, h:12 },
    // diploma
    { op:'r', color:'#e8e8f0', x:14, y:-5, w:10, h:14 },
    { op:'r', color:'#e63946', x:14, y:-5, w:10, h:3 },
  ],
};

function drawSprite(canvas, spriteKey, scale = 2) {
  const sprite = SPRITES[spriteKey];
  if (!sprite) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  sprite.forEach(({ op, color, x, y, w, h }) => {
    ctx.fillStyle = color;
    if (op === 'r') {
      ctx.fillRect(
        Math.floor(cx + x * scale - (w * scale) / 2),
        Math.floor(cy + y * scale - (h * scale) / 2),
        w * scale,
        h * scale
      );
    }
  });
}

/* ---- Item pixel icons ---- */
function drawItemIcon(canvas, color, shape) {
  const ctx = canvas.getContext('2d');
  const s = 2;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;

  // Glow
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;
  ctx.fillStyle = color;

  switch(shape) {
    case 'circle':
      ctx.beginPath();
      ctx.arc(cx, cy, 10*s, 0, Math.PI*2);
      ctx.fill();
      break;
    case 'star':
      drawStar(ctx, cx, cy, 5, 10*s, 5*s, color);
      break;
    case 'rect':
    default:
      ctx.fillRect(cx - 8*s, cy - 8*s, 16*s, 16*s);
  }
  ctx.shadowBlur = 0;

  // Inner dark
  ctx.fillStyle = 'rgba(0,0,0,0.4)';
  ctx.fillRect(cx - 5*s, cy - 5*s, 10*s, 10*s);
}

function drawStar(ctx, cx, cy, spikes, outerR, innerR) {
  let rot = (Math.PI / 2) * 3;
  const step = Math.PI / spikes;
  ctx.beginPath();
  ctx.moveTo(cx, cy - outerR);
  for (let i = 0; i < spikes; i++) {
    ctx.lineTo(cx + Math.cos(rot) * outerR, cy + Math.sin(rot) * outerR);
    rot += step;
    ctx.lineTo(cx + Math.cos(rot) * innerR, cy + Math.sin(rot) * innerR);
    rot += step;
  }
  ctx.lineTo(cx, cy - outerR);
  ctx.closePath();
  ctx.fill();
}

/* ---- Navbar ---- */
function initNavbar() {
  const toggle = document.querySelector('.nav-toggle');
  const links  = document.querySelector('.nav-links');
  if (toggle && links) {
    toggle.addEventListener('click', () => links.classList.toggle('open'));
    document.querySelectorAll('.nav-links a').forEach(a =>
      a.addEventListener('click', () => links.classList.remove('open'))
    );
  }

  // Active link
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (href === path || (path === '' && href === 'index.html')) {
      a.classList.add('active');
    }
  });
}

/* ---- Scroll animations ---- */
function initScrollAnim() {
  const els = document.querySelectorAll('[data-anim]');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('anim-in');
        observer.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });
  els.forEach(el => observer.observe(el));
}

/* ---- Notification ---- */
function showNotif(msg) {
  let n = document.querySelector('.notif');
  if (!n) {
    n = document.createElement('div');
    n.className = 'notif';
    document.body.appendChild(n);
  }
  n.textContent = '► ' + msg;
  n.classList.add('show');
  clearTimeout(n._t);
  n._t = setTimeout(() => n.classList.remove('show'), 3000);
}

/* ---- Contact form ---- */
function initContactForm() {
  const form = document.getElementById('contactForm');
  if (!form) return;
  form.addEventListener('submit', function(e) {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    btn.textContent = '...ОТПРАВКА...';
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = '✓ ОТПРАВЛЕНО!';
      btn.style.background = 'var(--green)';
      showNotif('Сообщение отправлено! Ответим скоро.');
      setTimeout(() => {
        form.reset();
        btn.textContent = 'ОТПРАВИТЬ';
        btn.style.background = '';
        btn.disabled = false;
      }, 3000);
    }, 1200);
  });
}

/* ---- Pixel hero canvas ---- */
function initHeroCanvas() {
  const canvas = document.getElementById('heroCanvas');
  if (!canvas) return;

  let frame = 0;
  let bobDir = 1;
  let bobY = 0;

  function draw() {
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const s = 3;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2 + bobY;

    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.4)';
    ctx.fillRect(cx - 14*s, cy + 14*s, 28*s, 4*s);

    // Body
    ctx.fillStyle = '#4cc9f0';
    ctx.fillRect(cx - 9*s, cy - 4*s, 18*s, 20*s);

    // Head
    ctx.fillStyle = '#f5d87a';
    ctx.fillRect(cx - 8*s, cy - 18*s, 16*s, 16*s);

    // Eyes blink
    if (frame % 120 < 5) {
      ctx.fillStyle = '#f5d87a'; // blinking — fill over eyes
      ctx.fillRect(cx - 5*s, cy - 15*s, 10*s, 3*s);
    } else {
      ctx.fillStyle = '#000';
      ctx.fillRect(cx - 5*s, cy - 15*s, 4*s, 4*s);
      ctx.fillRect(cx + 1*s, cy - 15*s, 4*s, 4*s);
    }

    // Bag
    ctx.fillStyle = '#2e2e4a';
    ctx.fillRect(cx + 10*s, cy - 4*s, 8*s, 14*s);
    ctx.fillStyle = '#6c6c8a';
    ctx.fillRect(cx + 11*s, cy - 2*s, 3*s, 3*s);

    // Projectile (report)
    const projX = cx + 30*s + ((frame * 2) % (canvas.width));
    ctx.fillStyle = '#f5c842';
    if (projX < canvas.width + 10) {
      ctx.fillRect(cx - projX % 180, cy - 8*s, 10*s, 8*s);
      ctx.fillStyle = '#c49a1a';
      ctx.fillRect(cx - projX % 180, cy - 8*s, 10*s, 2*s);
    }

    // Bob
    bobY += 0.08 * bobDir;
    if (Math.abs(bobY) > 3) bobDir *= -1;

    frame++;
    requestAnimationFrame(draw);
  }
  draw();
}

/* ---- Floor difficulty pips ---- */
function initFloorPips() {
  document.querySelectorAll('.floor-diff[data-level]').forEach(el => {
    const level = parseInt(el.dataset.level);
    el.innerHTML = '';
    for (let i = 1; i <= 5; i++) {
      const pip = document.createElement('div');
      pip.className = 'diff-pip' + (i <= level ? ' active' : '');
      el.appendChild(pip);
    }
  });
}

/* ---- Copy code blocks ---- */
function initCodeCopy() {
  document.querySelectorAll('code[data-copy]').forEach(el => {
    el.style.cursor = 'pointer';
    el.title = 'Нажмите, чтобы скопировать';
    el.addEventListener('click', () => {
      navigator.clipboard.writeText(el.textContent.trim()).then(() => {
        showNotif('Скопировано в буфер!');
      });
    });
  });
}

/* ---- Tab system ---- */
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.dataset.group;
      const target = btn.dataset.tab;
      document.querySelectorAll(`.tab-btn[data-group="${group}"]`).forEach(b => b.classList.remove('active'));
      document.querySelectorAll(`.tab-panel[data-group="${group}"]`).forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.querySelector(`.tab-panel[data-group="${group}"][data-tab="${target}"]`)?.classList.add('active');
    });
  });
}

/* ---- Counter animation ---- */
function animateCounter(el) {
  const target = parseInt(el.dataset.count);
  const dur = 1500;
  const step = dur / target;
  let cur = 0;
  const timer = setInterval(() => {
    cur += Math.ceil(target / 60);
    if (cur >= target) { cur = target; clearInterval(timer); }
    el.textContent = cur + (el.dataset.suffix || '');
  }, step > 16 ? step : 16);
}

function initCounters() {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        animateCounter(e.target);
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.5 });
  document.querySelectorAll('[data-count]').forEach(el => obs.observe(el));
}

/* ---- Konami code easter egg ---- */
function initKonami() {
  const code = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
  let pos = 0;
  document.addEventListener('keydown', e => {
    if (e.key === code[pos]) {
      pos++;
      if (pos === code.length) {
        showNotif('🎮 СЕКРЕТНЫЙ КОД АКТИВИРОВАН! Ты настоящий хакер МВЭК!');
        document.body.style.filter = 'hue-rotate(90deg)';
        setTimeout(() => document.body.style.filter = '', 2000);
        pos = 0;
      }
    } else {
      pos = 0;
    }
  });
}

/* ---- Init all ---- */
document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  initScrollAnim();
  initContactForm();
  initHeroCanvas();
  initFloorPips();
  initCodeCopy();
  initTabs();
  initCounters();
  initKonami();
});

// CSS for scroll animations (injected)
const style = document.createElement('style');
style.textContent = `
[data-anim] { opacity: 0; transform: translateY(24px); transition: opacity 0.5s ease, transform 0.5s ease; }
[data-anim].anim-in { opacity: 1; transform: translateY(0); }
[data-anim="left"] { transform: translateX(-24px); }
[data-anim="left"].anim-in { transform: translateX(0); }
[data-anim="right"] { transform: translateX(24px); }
[data-anim="right"].anim-in { transform: translateX(0); }

.tab-btn { font-family: var(--font-pixel); font-size: 8px; padding: 10px 16px; background: var(--bg-panel); color: var(--gray-light); border: 3px solid var(--border); cursor: pointer; transition: all 0.15s; }
.tab-btn.active { background: var(--gold); color: #000; border-color: var(--gold-dark); box-shadow: 3px 3px 0 var(--gold-dark); }
.tab-btn:hover:not(.active) { border-color: var(--gold); color: var(--gold); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.tabs-nav { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 24px; }
`;
document.head.appendChild(style);

// Скрываем .html из адресной строки
(function() {
  var titles = {
    'index.html':    'MVEK — College Roguelike',
    'about.html':    'Об игре — MVEK',
    'gameplay.html': 'Геймплей — MVEK',
    'team.html':     'Команда — MVEK',
    'download.html': 'Скачать — MVEK',
    'contact.html':  'Обратная связь — MVEK',
    'devlog.html':   'Devlog — MVEK'
  };

  function cleanURL() {
    var path = window.location.pathname;
    var file = path.split('/').pop();
    var title = titles[file];

    if (title && path.indexOf('.html') !== -1) {
      var cleanPath = path.replace('/' + file, '') || '/';
      history.replaceState(null, title, cleanPath);
      document.title = title;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', cleanURL);
  } else {
    cleanURL();
  }
})();