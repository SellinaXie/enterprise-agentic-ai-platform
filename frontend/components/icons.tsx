import type { SVGProps } from "react";

export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    dashboard: <><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></>,
    assessment: <><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4M9 12h6M9 16h6" /></>,
    add: <><path d="M12 5v14M5 12h14" /></>,
    review: <><path d="M4 12l5 5L20 6" /><path d="M4 4h16v16H4z" /></>,
    evaluation: <><path d="M5 20V10M12 20V4M19 20v-7" /></>,
    operations: <><path d="M4 18l5-6 4 3 7-9" /><path d="M4 4v16h16" /></>,
    shield: <><path d="M12 3l8 3v5c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6z" /><path d="M9 12l2 2 4-5" /></>,
    arrow: <><path d="M5 12h14M14 7l5 5-5 5" /></>,
    upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 15v5h16v-5" /></>,
    logout: <><path d="M10 4H4v16h6M14 8l4 4-4 4M8 12h10" /></>,
  };
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {paths[name] ?? paths.dashboard}
    </svg>
  );
}
