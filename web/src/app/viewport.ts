/**
 * The room is sized to the *visual* viewport, the part of the screen you can actually see.
 * When a phone keyboard opens, `100dvh` stays tall on iOS but the visual viewport shrinks,
 * so tracking it keeps the composer and the newest messages above the keyboard.
 * Writes one CSS variable (`--app-h`); no React state, no re-renders.
 */
export function trackVisualViewport(): void {
  const viewport = window.visualViewport;
  if (!viewport) return; // older browsers fall back to 100dvh in CSS

  const root = document.documentElement;
  let frame = 0;
  const update = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      root.style.setProperty('--app-h', `${Math.round(viewport.height)}px`);
      // iOS scrolls the page to reveal the focused input; keep the app pinned to the top.
      if (viewport.offsetTop > 0) window.scrollTo(0, 0);
    });
  };
  update();
  viewport.addEventListener('resize', update);
  viewport.addEventListener('scroll', update);
}
