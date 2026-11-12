import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlowSight — Real-Time Data Engineering & Predictive Analytics Platform",
  description: "End-to-end data platform demonstrating event ingestion, streaming replay, SQL transformations, ML demand forecasting, and monitoring.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 antialiased">{children}</body>
    </html>
  );
}

