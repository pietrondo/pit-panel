/* Sala del cane — menu, stato di apertura, galleria masonry, lightbox */
(function () {
  'use strict';

  /* ---------- menu mobile ---------- */
  var btn = document.querySelector('.menu-btn');
  var menu = document.getElementById('menu');
  if (btn && menu) {
    var chiudi = function () {
      menu.classList.remove('aperto');
      btn.setAttribute('aria-expanded', 'false');
    };
    btn.addEventListener('click', function () {
      var aperto = menu.classList.toggle('aperto');
      btn.setAttribute('aria-expanded', aperto ? 'true' : 'false');
    });
    menu.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') chiudi();
    });
    // Escape chiude il menu
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && menu.classList.contains('aperto')) {
        chiudi();
        btn.focus();
      }
    });
    // clic fuori dal menu lo chiude
    document.addEventListener('click', function (e) {
      if (!menu.classList.contains('aperto')) return;
      if (menu.contains(e.target) || btn.contains(e.target)) return;
      chiudi();
    });
  }

  /* ---------- orari ---------- */
  // [giorno JS: 0=domenica] -> fasce orarie
  var ORARI = {
    0: [],
    1: [['15:00', '19:30']],
    2: [['08:30', '12:30'], ['15:00', '19:30']],
    3: [['08:30', '12:30'], ['15:00', '19:30']],
    4: [['08:30', '12:30'], ['15:00', '19:30']],
    5: [['08:30', '12:30'], ['15:00', '19:30']],
    6: [['08:30', '12:30'], ['15:00', '19:30']]
  };

  var adesso = new Date();
  var oggi = adesso.getDay();

  var rigaOggi = document.querySelector('.orari__riga[data-giorno="' + oggi + '"]');
  if (rigaOggi) rigaOggi.classList.add('orari__riga--oggi');

  /* ---------- galleria masonry ---------- */
  var griglia = document.getElementById('galleria-griglia');
  var foto = window.FOTO_GALLERIA || [];

  if (griglia && foto.length) {
    var GAP = 16;

    griglia.style.position = 'relative';
    griglia.style.height = '0px';

    // 2 colonne su telefono, 3 su tablet, 4 su desktop.
    function colonnePer(larghezza) {
      if (larghezza < 620) return 2;
      if (larghezza < 900) return 3;
      return 4;
    }

    function costruisci() {
      var larghezza = griglia.clientWidth;
      if (!larghezza) return;

      var colonne = colonnePer(larghezza);
      var colWidth = (larghezza - GAP * (colonne - 1)) / colonne;
      var altezze = new Array(colonne).fill(0);

      griglia.innerHTML = '';
      foto.forEach(function (f, i) {
        var fig = document.createElement('figure');
        fig.style.position = 'absolute';
        fig.style.margin = '0';

        // panorama (foto dell'interno): occupa tutta la larghezza della griglia
        var panoramica = f.w / f.h >= 1.5;
        var w = panoramica ? larghezza : colWidth;
        fig.style.width = w + 'px';

        var h = Math.round(w * (f.h / f.w));
        var altezzaTotale = h + 34;

        if (panoramica) {
          var top = Math.max.apply(null, altezze);
          fig.style.left = '0px';
          fig.style.top = top + 'px';
          for (var c = 0; c < colonne; c++) altezze[c] = top + altezzaTotale + GAP;
        } else {
          // colonna piu' bassa
          var col = 0;
          for (var c = 1; c < colonne; c++) {
            if (altezze[c] < altezze[col]) col = c;
          }

          fig.style.left = col * (colWidth + GAP) + 'px';
          fig.style.top = altezze[col] + 'px';
          altezze[col] += altezzaTotale + GAP;
        }

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('aria-label', 'Ingrandisci ' + f.alt);
        btn.dataset.src = f.webp || f.src;

        var img = document.createElement('img');
        img.alt = f.alt;
        img.loading = 'lazy';
        img.decoding = 'async';
        img.width = f.w;
        img.height = f.h;
        img.style.width = '100%';
        img.style.height = 'auto';
        img.style.aspectRatio = f.w + ' / ' + f.h;

        if (f.webp) {
          var picture = document.createElement('picture');
          var sorgente = document.createElement('source');
          sorgente.srcset = f.webp;
          sorgente.type = 'image/webp';
          picture.appendChild(sorgente);
          picture.appendChild(img);
          btn.appendChild(picture);
        } else {
          img.src = f.src;
          btn.appendChild(img);
        }
        fig.appendChild(btn);

        var cap = document.createElement('figcaption');
        cap.textContent = f.alt;
        fig.appendChild(cap);

        griglia.appendChild(fig);
      });

      var totale = Math.max.apply(null, altezze) - GAP;
      griglia.style.height = Math.max(totale, 0) + 'px';
    }

    costruisci();

    var timer = null;
    window.addEventListener('resize', function () {
      clearTimeout(timer);
      timer = setTimeout(costruisci, 150);
    });

    /* ---------- lightbox ---------- */
    var lb = document.createElement('dialog');
    lb.className = 'lightbox';
    lb.innerHTML =
      '<button class="lightbox__chiudi" type="button" aria-label="Chiudi">Chiudi</button>' +
      '<img alt="">' +
      '<figcaption></figcaption>';
    document.body.appendChild(lb);

    griglia.addEventListener('click', function (e) {
      var btn = e.target.closest('button');
      if (!btn) return;
      var img = btn.querySelector('img');
      var grande = lb.querySelector('img');
      grande.src = btn.dataset.src;
      grande.alt = img ? img.alt : '';
      lb.querySelector('figcaption').textContent = img ? img.alt : '';
      lb.showModal();
    });

    lb.querySelector('.lightbox__chiudi').addEventListener('click', function () {
      lb.close();
    });
    lb.addEventListener('click', function (e) {
      if (e.target === lb) lb.close();
    });
  }
})();
