"use client";

import {
  useEffect,
  useRef,
  type CSSProperties,
  type ReactNode,
} from "react";

interface RevealProps {
  children: ReactNode;
  className?: string;
  delay?: number;
}

type RevealStyle = CSSProperties & {
  "--reveal-delay": string;
};

/**
 * Adds `.is-visible` when the wrapper enters the viewport.
 * The delay is handled by CSS, so no timer can outlive the component.
 */
export default function Reveal({
  children,
  className = "",
  delay = 0,
}: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    // Graceful fallback for older browsers or restricted environments.
    if (!("IntersectionObserver" in window)) {
      element.classList.add("is-visible");
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;

        element.classList.add("is-visible");
        observer.unobserve(element);
      },
      {
        threshold: 0.15,
        rootMargin: "0px 0px -40px 0px",
      },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const style: RevealStyle = {
    "--reveal-delay": `${Math.max(0, delay)}ms`,
  };

  return (
    <div ref={ref} className={`reveal ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
