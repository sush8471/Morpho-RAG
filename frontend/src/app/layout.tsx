import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Morpho-RAG — Grounded Academic Policy Assistant",
  description:
    "Grounded Academic Policy Q&A with strict attributions, amendment provenance, and zero-hallucination guardrails for Northfield Institute of Technology.",
  keywords: [
    "Academic Policy",
    "RAG",
    "Qdrant",
    "FastAPI",
    "Hybrid Retrieval",
    "BM25",
    "FlashRank",
    "Grounded Generation",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
