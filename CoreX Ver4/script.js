/* ===========================
   COREX NANO TECHNOLOGIES
   script.js
=========================== */

// === NAVBAR SCROLL ===
const navbar = document.getElementById('navbar');
const backToTop = document.getElementById('backToTop');

window.addEventListener('scroll', () => {
  if (window.scrollY > 60) {
    navbar.classList.add('scrolled');
    backToTop.classList.add('visible');
  } else {
    navbar.classList.remove('scrolled');
    backToTop.classList.remove('visible');
  }
});

backToTop.addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// === HAMBURGER MENU ===
const hamburger = document.getElementById('hamburger');
const navLinks  = document.getElementById('navLinks');

hamburger.addEventListener('click', () => {
  hamburger.classList.toggle('active');
  navLinks.classList.toggle('open');
});

navLinks.querySelectorAll('a').forEach(link => {
  link.addEventListener('click', () => {
    hamburger.classList.remove('active');
    navLinks.classList.remove('open');
  });
});

// === SMOOTH SCROLL FOR NAV LINKS ===
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function(e) {
    const href = this.getAttribute('href');
    if (href === '#') return;
    const target = document.querySelector(href);
    if (target) {
      e.preventDefault();
      const offset = 72;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  });
});

// === PARTICLE CANVAS ===
const canvas = document.getElementById('particleCanvas');
if (canvas) {
  const ctx = canvas.getContext('2d');
  let particles = [];
  let animId;

  function resizeCanvas() {
    canvas.width  = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
  }

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x    = Math.random() * canvas.width;
      this.y    = Math.random() * canvas.height;
      this.vx   = (Math.random() - 0.5) * 0.4;
      this.vy   = (Math.random() - 0.5) * 0.4;
      this.size = Math.random() * 1.5 + 0.5;
      this.alpha= Math.random() * 0.6 + 0.2;
    }
    update() {
      this.x += this.vx; this.y += this.vy;
      if (this.x < 0 || this.x > canvas.width || this.y < 0 || this.y > canvas.height) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(46, 127, 255, ${this.alpha})`;
      ctx.fill();
    }
  }

  function initParticles() {
    particles = [];
    const count = Math.floor((canvas.width * canvas.height) / 12000);
    for (let i = 0; i < count; i++) particles.push(new Particle());
  }

  function drawConnections() {
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx   = particles[i].x - particles[j].x;
        const dy   = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(46, 127, 255, ${0.12 * (1 - dist / 120)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
  }

  function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => { p.update(); p.draw(); });
    drawConnections();
    animId = requestAnimationFrame(animate);
  }

  window.addEventListener('resize', () => { resizeCanvas(); initParticles(); });
  resizeCanvas();
  initParticles();
  animate();
}

// === COUNTER ANIMATION ===
function animateCounter(el) {
  const target = parseInt(el.dataset.target, 10);
  const duration = 2000;
  const start = performance.now();

  function update(now) {
    const elapsed  = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased    = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.floor(eased * target);
    if (progress < 1) requestAnimationFrame(update);
    else el.textContent = target;
  }
  requestAnimationFrame(update);
}

// === METER BAR ANIMATION ===
function animateMeter(el) {
  const width = el.dataset.width;
  el.style.width = width + '%';
}

// === INTERSECTION OBSERVER ===
const observerOptions = { threshold: 0.15, rootMargin: '0px 0px -60px 0px' };

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');

      // Counters
      entry.target.querySelectorAll('.stat-num').forEach(el => animateCounter(el));

      // Meter bars
      entry.target.querySelectorAll('.meter-fill').forEach(el => animateMeter(el));

      observer.unobserve(entry.target);
    }
  });
}, observerOptions);

// Add fade-in to elements
document.querySelectorAll(
  '.service-card, .area-card, .diff-item, .hero-stats, .atuacao-intro, .highlight-item, .contato-info, .contato-form-box'
).forEach((el, i) => {
  el.classList.add('fade-in');
  el.style.transitionDelay = `${(i % 4) * 80}ms`;
  observer.observe(el);
});

// Also observe hero stats for counter
const heroStats = document.querySelector('.hero-stats');
if (heroStats) observer.observe(heroStats);

// === FORM SUBMIT ===
const form = document.getElementById('contatoForm');
const formSuccess = document.getElementById('formSuccess');

if (form) {
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const btn = form.querySelector('.btn-form');
    btn.disabled = true;
    btn.querySelector('.btn-form-text').textContent = 'ENVIANDO...';

    setTimeout(() => {
      formSuccess.classList.add('show');
      btn.querySelector('.btn-form-text').textContent = 'ENVIADO ✓';
      btn.style.background = 'rgba(74, 222, 128, 0.2)';
      btn.style.borderColor = 'rgba(74, 222, 128, 0.5)';
      form.reset();
      setTimeout(() => {
        formSuccess.classList.remove('show');
        btn.disabled = false;
        btn.querySelector('.btn-form-text').textContent = 'ENVIAR MENSAGEM';
        btn.style.background = '';
        btn.style.borderColor = '';
      }, 5000);
    }, 1200);
  });
}

// === CARD GLOW MOUSE EFFECT ===
document.querySelectorAll('.service-card').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top)  / rect.height) * 100;
    const glow = card.querySelector('.card-glow');
    if (glow) glow.style.background = `radial-gradient(circle at ${x}% ${y}%, rgba(46,127,255,0.12), transparent 60%)`;
  });
  card.addEventListener('mouseleave', () => {
    const glow = card.querySelector('.card-glow');
    if (glow) glow.style.background = '';
  });
});

// === ACTIVE NAV LINK ON SCROLL ===
const sections = document.querySelectorAll('section[id]');
const navItems = document.querySelectorAll('.nav-link');

window.addEventListener('scroll', () => {
  let current = '';
  sections.forEach(section => {
    const top = section.offsetTop - 120;
    if (window.scrollY >= top) current = section.getAttribute('id');
  });
  navItems.forEach(link => {
    link.style.color = '';
    if (link.getAttribute('href') === `#${current}`) {
      link.style.color = 'var(--white)';
    }
  });
}, { passive: true });


    (function() {
      const btn = document.getElementById('themeToggle');
      const body = document.body;
      const STORAGE_KEY = 'corex-theme';

      // Restore saved preference
      if (localStorage.getItem(STORAGE_KEY) === 'light') {
        body.classList.add('light-theme');
      }

      btn.addEventListener('click', function() {
        const isLight = body.classList.toggle('light-theme');
        localStorage.setItem(STORAGE_KEY, isLight ? 'light' : 'dark');
      });
    })();
 