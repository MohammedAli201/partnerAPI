import { useEffect } from "react";
import Lenis from "lenis";

let instance = null;

export const scrollToId = (id) => {
  const el = document.getElementById(id.replace(/^#/, ""));
  if (!el) return;
  if (instance) instance.scrollTo(el, { offset: -72, duration: 1.4 });
  else el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
};

export const useLenis = () => {
  useEffect(() => {
    if(window.matchMedia("(prefers-reduced-motion: reduce)").matches)return;
    const lenis = new Lenis({ lerp: 0.09, smoothWheel: true });
    instance = lenis;window.__lenis=lenis;
    let raf;
    const loop = (t) => {
      lenis.raf(t);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      lenis.destroy();
      instance = null;if(window.__lenis===lenis)window.__lenis=null;
    };
  }, []);
};
