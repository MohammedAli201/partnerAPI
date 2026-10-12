import { motion } from "framer-motion";
import { fadeUp, stagger, viewport } from "@/lib/motion";

export const SectionHeader = ({ eyebrow, title, lead, align = "left", dark = false, className = "" }) => (
  <motion.div
    variants={stagger(0.1)}
    initial="hidden"
    whileInView="show"
    viewport={viewport}
    className={`section-heading ${align === "center" ? "mx-auto text-center" : ""} max-w-[720px] ${className}`}
  >
    <motion.p variants={fadeUp} className={`eyebrow ${dark ? "text-teal-300" : ""}`}>
      {eyebrow}
    </motion.p>
    <motion.h2 variants={fadeUp} className={`h2 mt-5 ${dark ? "text-white" : ""}`}>
      {title}
    </motion.h2>
    {lead && (
      <motion.p variants={fadeUp} className={`lead mt-6 ${dark ? "text-slate-400" : ""}`}>
        {lead}
      </motion.p>
    )}
  </motion.div>
);
