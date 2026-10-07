"use client";

import React from "react";
import { FileText } from "lucide-react";
import { Citation } from "@/lib/types";

interface AmendmentBannerProps {
  citations: Citation[];
}

export const AmendmentBanner: React.FC<AmendmentBannerProps> = ({ citations }) => {
  const hasAmendment1 = citations.some((c) => {
    const q = (c.verbatim_quote || c.quote || "").toLowerCase();
    return (
      c.section_id === "5.5.2" ||
      q.includes("amendment 1") ||
      q.includes("500 mrl") ||
      q.includes("500")
    );
  });
  const hasAmendment2 = citations.some((c) => {
    const q = (c.verbatim_quote || c.quote || "").toLowerCase();
    return (
      c.section_id === "7.2" ||
      q.includes("amendment 2") ||
      q.includes("3,000")
    );
  });

  if (!hasAmendment1 && !hasAmendment2) return null;

  return (
    <div
      style={{
        marginTop: "10px",
        marginBottom: "8px",
        padding: "12px 14px",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "rgba(245, 158, 11, 0.06)",
        border: "1px solid rgba(245, 158, 11, 0.22)",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <FileText size={14} color="var(--warning)" />
        <span
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: "var(--warning)",
          }}
        >
          Active policy amendment applied
        </span>
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "4px",
          fontSize: "13px",
          color: "var(--text-secondary)",
          lineHeight: 1.5,
        }}
      >
        {hasAmendment1 && (
          <div>
            <span style={{ color: "var(--warning)", fontWeight: 500 }}>
              Amendment 1 (1 Aug 2025):
            </span>{" "}
            Re-evaluation fee amended to MRL 500 per theory course (supersedes MRL 300 in Section 5.5.2).
          </div>
        )}
        {hasAmendment2 && (
          <div>
            <span style={{ color: "var(--warning)", fontWeight: 500 }}>
              Amendment 2 (1 Feb 2026):
            </span>{" "}
            Late tuition fee amended to MRL 500 per week, capped at MRL 3,000 (supersedes MRL 100/day in Section 7.2).
          </div>
        )}
      </div>
    </div>
  );
};
