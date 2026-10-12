import "../supplied-landing-theme.css";
import { useLenis } from "@/hooks/useLenis";
import { Nav } from "@/components/landing/Nav";
import { Hero } from "@/components/landing/Hero";
import { Marquee } from "@/components/landing/Marquee";
import { Coverage } from "@/components/landing/Coverage";
import { WhyHubaal } from "@/components/landing/WhyHubaal";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Exceptions } from "@/components/landing/Exceptions";
import { Trust } from "@/components/landing/Trust";
import { About } from "@/components/landing/About";
import { Integration } from "@/components/landing/Integration";
import { Enquiry } from "@/components/landing/Enquiry";
import { Footer } from "@/components/landing/Footer";

export default function Landing() {
  useLenis();
  return (
    <div className="source-landing relative overflow-x-clip bg-canvas">
      <Nav />
      <main id="main" tabIndex={-1} data-testid="landing-page">
      <Hero />
      <Marquee />
      <Coverage />
      <WhyHubaal />
      <HowItWorks />
      <Exceptions />
      <Trust />
      <About />
      <Integration />
      <Enquiry />
      </main>
      <Footer />
    </div>
  );
}
