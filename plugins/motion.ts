type MotionElement = HTMLElement & {
  __siliciumCleanup?: () => void;
};

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// A card with form fields does not move under the pointer: tilting a form
// while the user types is uncomfortable, and redrawing its blurred glass
// on every pointer move made the settings page slow.
const hasFormFields = (element: HTMLElement) => element.querySelector('input, textarea, select') !== null;

/**
 * `handler` at most once per animation frame, with the last event: a pointer
 * fires far more moves than the screen draws frames.
 */
function perFrame(handler: (event: PointerEvent) => void): (event: PointerEvent) => void {
  let pending: PointerEvent | null = null;
  return (event) => {
    if (pending) { pending = event; return; }
    pending = event;
    requestAnimationFrame(() => {
      const last = pending;
      pending = null;
      if (last) handler(last);
    });
  };
}

// UiCard owns the v-tilt interaction. Keeping it out of the generic spatial
// scan prevents two pointer handlers from writing the same transform variables
// and producing a doubled depth/parallax effect.
const spatialSelector = '.spatial-tile, .marketing-glass, .surface, .glass-panel, .public-header__mobile';

function resetSpatial(element: HTMLElement) {
  element.style.setProperty('--tilt-x', '0deg');
  element.style.setProperty('--tilt-y', '0deg');
  element.style.setProperty('--spatial-z', '0px');
  element.style.setProperty('--spatial-scale', '1');
  element.style.setProperty('--spatial-blur', '0px');
  element.style.setProperty('--spatial-parallax-x', '0px');
  element.style.setProperty('--spatial-parallax-y', '0px');
  element.style.setProperty('--spatial-light-x', '50%');
  element.style.setProperty('--spatial-light-y', '50%');
  delete element.dataset.spatialActive;
}

function bindSpatialTile(element: HTMLElement) {
  if (element.dataset.spatialBound === 'true') return () => undefined;
  element.dataset.spatialBound = 'true';
  element.classList.add('spatial-tile');
  resetSpatial(element);

  const move = perFrame((event: PointerEvent) => {
    if (event.pointerType === 'touch' || hasFormFields(element)) return;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    const distance = Math.min(1, Math.hypot(x - .5, y - .5) / .72);
    const focus = 1 - distance;
    element.style.setProperty('--tilt-x', `${((.5 - y) * 3.2).toFixed(2)}deg`);
    element.style.setProperty('--tilt-y', `${((x - .5) * 4.2).toFixed(2)}deg`);
    element.style.setProperty('--spatial-z', `${(10 + focus * 42).toFixed(1)}px`);
    element.style.setProperty('--spatial-scale', `${(1 + focus * .012).toFixed(4)}`);
    element.style.setProperty('--spatial-blur', `${((1 - focus) * .35).toFixed(2)}px`);
    element.style.setProperty('--spatial-parallax-x', `${((x - .5) * -14).toFixed(1)}px`);
    element.style.setProperty('--spatial-parallax-y', `${((y - .5) * -14).toFixed(1)}px`);
    element.style.setProperty('--spatial-light-x', `${(x * 100).toFixed(1)}%`);
    element.style.setProperty('--spatial-light-y', `${(y * 100).toFixed(1)}%`);
    element.dataset.spatialActive = 'true';
  });
  const reset = () => resetSpatial(element);
  element.addEventListener('pointermove', move);
  element.addEventListener('pointerleave', reset);
  return () => {
    element.removeEventListener('pointermove', move);
    element.removeEventListener('pointerleave', reset);
    delete element.dataset.spatialBound;
    resetSpatial(element);
  };
}

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.directive('reveal', {
    getSSRProps: () => ({}),
    mounted(element: MotionElement, binding) {
      element.dataset.reveal = typeof binding.value === 'string' ? binding.value : '';
      if (binding.value && typeof binding.value === 'object' && binding.value.delay) {
        element.style.setProperty('--reveal-delay', `${binding.value.delay}ms`);
      }
      if (reducedMotion() || !('IntersectionObserver' in window)) {
        element.classList.add('is-visible');
        return;
      }
      const observer = new IntersectionObserver(([entry]) => {
        if (!entry?.isIntersecting) return;
        element.classList.add('is-visible');
        observer.disconnect();
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
      observer.observe(element);
      element.__siliciumCleanup = () => observer.disconnect();
    },
    unmounted(element: MotionElement) {
      element.__siliciumCleanup?.();
    },
  });

  nuxtApp.vueApp.directive('tilt', {
    getSSRProps: () => ({}),
    mounted(element: MotionElement, binding) {
      if (binding.value === false || reducedMotion()) return;
      const strength = typeof binding.value === 'number' ? binding.value : 4;
      const move = perFrame((event: PointerEvent) => {
        if (hasFormFields(element)) return;
        const rect = element.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width;
        const y = (event.clientY - rect.top) / rect.height;
        const focus = Math.max(0, 1 - Math.min(1, Math.hypot(x - .5, y - .5) / .72));
        element.style.setProperty('--tilt-x', `${(0.5 - y) * strength}deg`);
        element.style.setProperty('--tilt-y', `${(x - 0.5) * strength}deg`);
        element.style.setProperty('--spatial-z', `${(10 + focus * 42).toFixed(1)}px`);
        element.style.setProperty('--spatial-scale', `${(1 + focus * .012).toFixed(4)}`);
        element.style.setProperty('--spatial-blur', `${((1 - focus) * .35).toFixed(2)}px`);
        element.style.setProperty('--spatial-parallax-x', `${((x - .5) * -14).toFixed(1)}px`);
        element.style.setProperty('--spatial-parallax-y', `${((y - .5) * -14).toFixed(1)}px`);
        element.style.setProperty('--glow-x', `${x * 100}%`);
        element.style.setProperty('--glow-y', `${y * 100}%`);
        element.style.setProperty('--spatial-light-x', `${x * 100}%`);
        element.style.setProperty('--spatial-light-y', `${y * 100}%`);
        element.dataset.tilting = 'true';
      });
      const reset = () => {
        element.style.setProperty('--tilt-x', '0deg');
        element.style.setProperty('--tilt-y', '0deg');
        element.style.setProperty('--spatial-z', '0px');
        element.style.setProperty('--spatial-scale', '1');
        element.style.setProperty('--spatial-blur', '0px');
        element.style.setProperty('--spatial-parallax-x', '0px');
        element.style.setProperty('--spatial-parallax-y', '0px');
        delete element.dataset.tilting;
      };
      element.addEventListener('pointermove', move);
      element.addEventListener('pointerleave', reset);
      element.__siliciumCleanup = () => {
        element.removeEventListener('pointermove', move);
        element.removeEventListener('pointerleave', reset);
      };
    },
    unmounted(element: MotionElement) {
      element.__siliciumCleanup?.();
    },
  });

  nuxtApp.vueApp.directive('spatial', {
    getSSRProps: () => ({}),
    mounted(element: MotionElement) {
      if (reducedMotion()) return;
      const cleanups = new Map<HTMLElement, () => void>();
      const scan = () => {
        for (const [tile, cleanup] of cleanups) {
          if (!element.contains(tile)) {
            cleanup();
            cleanups.delete(tile);
          }
        }
        element.querySelectorAll<HTMLElement>(spatialSelector).forEach(tile => {
          if (!cleanups.has(tile)) cleanups.set(tile, bindSpatialTile(tile));
        });
      };
      scan();
      const observer = new MutationObserver(scan);
      observer.observe(element, { childList: true, subtree: true });
      element.__siliciumCleanup = () => {
        observer.disconnect();
        cleanups.forEach(cleanup => cleanup());
        cleanups.clear();
      };
    },
    unmounted(element: MotionElement) {
      element.__siliciumCleanup?.();
    },
  });
});
