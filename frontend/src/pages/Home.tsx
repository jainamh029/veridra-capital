import { MarketingNav } from "@/components/layout/MarketingNav";
import { Footer } from "@/components/layout/Footer";
import { Hero } from "@/components/home/Hero";
import { ModulesShowcase } from "@/components/home/ModulesShowcase";
import { PipelineFlow } from "@/components/home/PipelineFlow";
import { ResultsSection } from "@/components/home/ResultsSection";
import { TrustSection } from "@/components/home/TrustSection";
import { CTASection } from "@/components/home/CTASection";

export default function Home() {
  return (
    <div className="veridra-dark bg-ink-900">
      <MarketingNav />
      <Hero />
      <ModulesShowcase />
      <PipelineFlow />
      <ResultsSection />
      <TrustSection />
      <CTASection />
      <Footer />
    </div>
  );
}
