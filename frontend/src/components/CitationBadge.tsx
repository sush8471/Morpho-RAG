"use client";

import React from "react";
import { Citation } from "@/lib/types";

interface CitationBadgeProps {
  citation: Citation;
  onClick: (citation: Citation) => void;
  index?: number;
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({
  citation,
  onClick,
}) => {
  const isAmendment =
    citation.section_id === "5.5.2" ||
    citation.section_id === "7.2" ||
    citation.section_title.toLowerCase().includes("amendment");

  const pageLabel = citation.page ? ` · p. ${citation.page}` : "";

  return (
    <button
      onClick={() => onClick(citation)}
      className={`citation-pill ${isAmendment ? "amendment" : ""}`}
      title={`Inspect verbatim passage for Section ${citation.section_id}: ${citation.section_title}`}
      type="button"
    >
      <span>[§ {citation.section_id}{pageLabel}]</span>
    </button>
  );
};
