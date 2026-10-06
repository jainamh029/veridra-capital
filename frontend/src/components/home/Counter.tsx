import { useEffect, useRef } from "react";
import { motion, useInView, useMotionValue, useSpring } from "framer-motion";

export function Counter({ to, decimals = 0, suffix = "", prefix = "" }: {
  to: number; decimals?: number; suffix?: string; prefix?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const motionVal = useMotionValue(0);
  const spring = useSpring(motionVal, { damping: 24, stiffness: 90 });

  useEffect(() => {
    if (inView) motionVal.set(to);
  }, [inView, to, motionVal]);

  useEffect(() => {
    return spring.on("change", (v) => {
      if (ref.current) {
        ref.current.textContent = `${prefix}${v.toLocaleString("en-US", {
          minimumFractionDigits: decimals, maximumFractionDigits: decimals,
        })}${suffix}`;
      }
    });
  }, [spring, decimals, prefix, suffix]);

  return <motion.span ref={ref}>{prefix}0{suffix}</motion.span>;
}
