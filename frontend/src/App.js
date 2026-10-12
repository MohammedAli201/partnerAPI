import { useEffect } from "react";
import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import LegalPage from "@/components/LegalPage";
import { BusinessContext } from "./business";
import { PublicPage } from "./components/PublicPages";
import "./site-theme.css";
import "./reference-typography.css";
import Landing from "./pages/Landing";
import { Toaster } from "sonner";

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

const Home = () => <Landing />;

function NavigationEffects() {
 const {pathname,hash}=useLocation();
 const navigate=useNavigate();
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
  const go=()=>{
    if(!active)return;
    if(pathname==='/' && hash==='#faq'){navigate('/help',{replace:true});return;}
    if(hash){const id=decodeURIComponent(hash.slice(1));const aliases={top:'hero',channels:'coverage',api:'integration','partner-form':'enquiry',values:'about'};(document.getElementById(id)||document.getElementById(aliases[id]))?.scrollIntoView();}
    else window.scrollTo(0,0);
  };
  go();document.fonts.ready.then(go);
  return()=>{active=false;};
 },[pathname,hash,navigate]);
 return null;
}

function App({business}) {

  return (
    <div className="App bg-void min-h-screen">
      <BusinessContext.Provider value={business}><BrowserRouter>
        <NavigationEffects />
        <MotionConfig reducedMotion="user">
          <Toaster position="bottom-right" richColors closeButton />
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/privacy" element={<><LegalPage kind="privacy" /><Footer /></>} />
              <Route path="/terms" element={<><LegalPage kind="terms" /><Footer /></>} />
              {['/receive','/partners','/about','/help','/contact','/track','/complaints','/partners/integration'].map(path=><Route key={path} path={path} element={<><Nav/><main id="main" tabIndex="-1" className="hubaal-site pt-[72px]"><PublicPage path={path}/></main><Footer/></>}/>)}
            </Routes>
          </ErrorBoundary>
        </MotionConfig>
      </BrowserRouter></BusinessContext.Provider>
    </div>
  );
}

export default App;
