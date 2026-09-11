/* Arsha main.js (trimmed for GeoNode homepage: header/nav/scroll-top/AOS/scrollspy only). */
(function() {
  "use strict";

  function toggleScrolled() {
    var selectBody = document.querySelector('body');
    var selectHeader = document.querySelector('#header');
    if (!selectHeader) return;
    if (!selectHeader.classList.contains('scroll-up-sticky') && !selectHeader.classList.contains('sticky-top') && !selectHeader.classList.contains('fixed-top')) return;
    if (window.scrollY > 100) { selectBody.classList.add('scrolled'); }
    else { selectBody.classList.remove('scrolled'); }
  }
  document.addEventListener('scroll', toggleScrolled);
  window.addEventListener('load', toggleScrolled);

  var mobileNavToggleBtn = document.querySelector('.mobile-nav-toggle');
  function mobileNavToogle() {
    document.querySelector('body').classList.toggle('mobile-nav-active');
    if (mobileNavToggleBtn) {
      mobileNavToggleBtn.classList.toggle('bi-list');
      mobileNavToggleBtn.classList.toggle('bi-x');
    }
  }
  if (mobileNavToggleBtn) {
    mobileNavToggleBtn.addEventListener('click', mobileNavToogle);
  }

  document.querySelectorAll('#navmenu a').forEach(function(navmenu) {
    navmenu.addEventListener('click', function() {
      if (document.querySelector('.mobile-nav-active')) {
        mobileNavToogle();
      }
    });
  });

  document.querySelectorAll('.navmenu .toggle-dropdown').forEach(function(el) {
    el.addEventListener('click', function(e) {
      e.preventDefault();
      this.parentNode.classList.toggle('active');
      if (this.parentNode.nextElementSibling) {
        this.parentNode.nextElementSibling.classList.toggle('dropdown-active');
      }
      e.stopImmediatePropagation();
    });
  });

  var scrollTop = document.querySelector('.scroll-top');
  function toggleScrollTop() {
    if (scrollTop) {
      if (window.scrollY > 100) { scrollTop.classList.add('active'); }
      else { scrollTop.classList.remove('active'); }
    }
  }
  if (scrollTop) {
    scrollTop.addEventListener('click', function(e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
  window.addEventListener('load', toggleScrollTop);
  document.addEventListener('scroll', toggleScrollTop);

  function aosInit() {
    if (typeof AOS === 'undefined') return;
    AOS.init({ duration: 600, easing: 'ease-in-out', once: true, mirror: false });
  }
  window.addEventListener('load', aosInit);

  window.addEventListener('load', function(e) {
    if (window.location.hash) {
      var target = null;
      try { target = document.querySelector(window.location.hash); } catch (err) { target = null; }
      if (target) {
        setTimeout(function() {
          var scrollMarginTop = getComputedStyle(target).scrollMarginTop;
          window.scrollTo({ top: target.offsetTop - parseInt(scrollMarginTop), behavior: 'smooth' });
        }, 100);
      }
    }
  });

  var navmenulinks = document.querySelectorAll('.navmenu a');
  function navmenuScrollspy() {
    navmenulinks.forEach(function(navmenulink) {
      if (!navmenulink.hash) return;
      var section = null;
      try { section = document.querySelector(navmenulink.hash); } catch (err) { section = null; }
      if (!section) return;
      var position = window.scrollY + 200;
      if (position >= section.offsetTop && position <= (section.offsetTop + section.offsetHeight)) {
        document.querySelectorAll('.navmenu a.active').forEach(function(link) { link.classList.remove('active'); });
        navmenulink.classList.add('active');
      } else {
        navmenulink.classList.remove('active');
      }
    });
  }
  window.addEventListener('load', navmenuScrollspy);
  document.addEventListener('scroll', navmenuScrollspy);
})();
