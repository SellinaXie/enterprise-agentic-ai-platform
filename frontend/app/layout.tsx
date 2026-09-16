import type { Metadata } from "next";

import { ExperienceShell } from "@/components/experience-shell";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Enterprise AI Risk Intelligence",
    template: "%s | Enterprise AI Risk Intelligence",
  },
  description: "Evidence-grounded enterprise AI architecture, risk, governance, and review.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ExperienceShell>{children}</ExperienceShell>
      </body>
    </html>
  );
}
