import { useEffect } from "react";
import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import Lenis from "lenis";
import Nav from "@/components/Nav";
import Hero from "@/components/Hero";
import StatsBand from "@/components/StatsBand";
import Channels from "@/components/Channels";
import HowItWorks from "@/components/HowItWorks";
import PartnerApi from "@/components/PartnerApi";
import PartnerBand from "@/components/PartnerBand";
import About from "@/components/About";
import Faq from "@/components/Faq";
import PartnershipForm from "@/components/PartnershipForm";
import Footer from "@/components/Footer";
import LegalPage from "@/components/LegalPage";
import { BusinessContext } from "./business";
import { PublicPage } from "./components/PublicPages";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-void text-ink-light">
          Something went wrong. Please refresh the page.
        </div>
      );
    }
    return this.props.children;
  }
}

const Home = () => (
  <>
    <Nav />
    <main id="main" tabIndex="-1">
      <Hero />
      <StatsBand />
      <Channels />
      <PartnerBand />
      <HowItWorks />
      <PartnerApi />
      <About />
      <Faq />
      <PartnershipForm />
    </main>
    <Footer />
  </>
);

function NavigationEffects() {
 const {pathname,hash}=useLocation();
 const business=React.useContext(BusinessContext);
 useEffect(()=>{
  const companyTitles={'/':'Your payout partner in Somalia.','/about':'About Hubaal','/help':'Partner support','/contact':'Contact partner operations','/privacy':'Privacy Policy','/terms':'Terms of Service'};
  const title=business.lang==='en'&&companyTitles[pathname]?companyTitles[pathname]:business.titles?.[pathname];
  if(title)document.title=`${title} · ${business.brand}`;
  const description=document.querySelector('meta[name="description"]');
  if(description&&business.descriptions?.[pathname])description.content=business.descriptions[pathname];
  const shareTitle=document.querySelector('meta[property="og:title"]');
  if(shareTitle)shareTitle.content=document.title;
  const shareDescription=document.querySelector('meta[property="og:description"]');
  if(shareDescription&&description)shareDescription.content=description.content;
 },[pathname,business]);
 useEffect(()=>{
  let active=true;
  const go=()=>{if(!active)return;if(hash)document.getElementById(hash==="#integration"?"api":hash==="#coverage"?"channels":decodeURIComponent(hash.slice(1)))?.scrollIntoView();else window.scrollTo(0,0);};
  go();document.fonts.ready.then(go);
  return()=>{active=false;};
 },[pathname,hash]);
 return null;
}

function App({business}) {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ lerp: 0.09, wheelMultiplier: 1 });
    window.__lenis = lenis;
    let rafId;
    const raf = (time) => {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    };
    rafId = requestAnimationFrame(raf);

    const onClick = (e) => {
      const anchor = e.target.closest('a[href]');
      if (!anchor) return;
      const target = new URL(anchor.href, window.location.href);
      if (target.origin !== window.location.origin || target.pathname !== window.location.pathname || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      const hash = target.hash;
      if(hash==="#main")return;
      if (hash.length < 2) return;
      const el = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (!el) return;
      e.preventDefault();
      history.pushState(null,"",hash);
      lenis.scrollTo(el, { duration: 1.4, force: true });
    };
    document.addEventListener("click", onClick);

    return () => {
      cancelAnimationFrame(rafId);
      document.removeEventListener("click", onClick);
      lenis.destroy();
      window.__lenis = null;
    };
  }, []);

  return (
    <div className="App bg-void min-h-screen">
      <BusinessContext.Provider value={business}><BrowserRouter>
        <NavigationEffects />
        <MotionConfig reducedMotion="user">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/privacy" element={<><LegalPage kind="privacy" /><Footer /></>} />
              <Route path="/terms" element={<><LegalPage kind="terms" /><Footer /></>} />
              {['/receive','/partners','/about','/help','/contact','/track','/complaints','/partners/integration'].map(path=><Route key={path} path={path} element={<><Nav/><main id="main" tabIndex="-1" className="pt-[72px]"><PublicPage path={path}/></main><Footer/></>}/>)}
            </Routes>
          </ErrorBoundary>
        </MotionConfig>
      </BrowserRouter></BusinessContext.Provider>
    </div>
  );
}

export default App;
