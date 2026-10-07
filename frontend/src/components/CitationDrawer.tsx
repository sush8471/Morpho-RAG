"use client";

import React, { useState, useEffect } from "react";
import { X, Copy, Check, FileText } from "lucide-react";
import { Citation } from "@/lib/types";

interface CitationDrawerProps {
  citation: Citation | null;
  onClose: () => void;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({ citation, onClose }) => {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!citation) return null;

  const isAmendment =
    citation.section_id === "5.5.2" ||
    citation.section_id === "7.2" ||
    citation.section_title.toLowerCase().includes("amendment");

  const handleCopyQuote = async () => {
    try {
      await navigator.clipboard.writeText(citation.verbatim_quote);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error("Failed to copy quote: ", e);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        justifyContent: "flex-end",
        backgroundColor: "rgba(0, 0, 0, 0.55)",
      }}
      onClick={onClose}
    >
      <div
        className="animate-fade"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: "420px",
          height: "100%",
          backgroundColor: "var(--surface-1)",
          borderLeft: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          padding: "24px 20px",
          overflowY: "auto",
        }}
      >
        {/* Drawer header */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            borderBottom: "1px solid var(--border)",
            paddingBottom: "16px",
            marginBottom: "20px",
            gap: "12px",
          }}
        >
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: isAmendment ? "var(--warning)" : "var(--accent)",
                marginBottom: "4px",
              }}
            >
              <span>section {citation.section_id}</span>
              {citation.page && (
                <span className="tabular-nums" style={{ color: "var(--text-muted)" }}>
                  · page {citation.page}
                </span>
              )}
            </div>
            <h2
              style={{
                fontFamily: "var(--font-heading)",
                fontSize: "1.05rem",
                fontWeight: 600,
                color: "var(--text-primary)",
                lineHeight: 1.35,
              }}
            >
              {citation.section_title}
            </h2>
          </div>

          <button
            onClick={onClose}
            aria-label="Close drawer"
            style={{
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: "6px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Amendment notice if applicable */}
        {isAmendment && (
          <div
            style={{
              padding: "12px 14px",
              borderRadius: "var(--radius-sm)",
              backgroundColor: "rgba(245, 158, 11, 0.08)",
              border: "1px solid rgba(245, 158, 11, 0.22)",
              marginBottom: "16px",
              fontSize: "13px",
              lineHeight: 1.5,
              color: "var(--warning)",
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: "2px" }}>
              Amended policy clause
            </div>
            <div style={{ color: "var(--text-secondary)", fontSize: "12px" }}>
              This section is subject to an active handbook amendment superseding the baseline clause.
            </div>
          </div>
        )}

        {/* Verbatim quote body */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", flex: 1 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span
              style={{
                fontSize: "12px",
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
              }}
            >
              verbatim handbook passage
            </span>

            <button
              onClick={handleCopyQuote}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                background: "transparent",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "4px 8px",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
                color: copied ? "var(--positive)" : "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              <span>{copied ? "copied" : "copy passage"}</span>
            </button>
          </div>

          <div
            style={{
              backgroundColor: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "16px",
              fontSize: "14px",
              lineHeight: 1.65,
              color: "var(--text-primary)",
              whiteSpace: "pre-wrap",
            }}
          >
            {citation.verbatim_quote}
          </div>
        </div>

        {/* Handbook footer reference */}
        <div
          style={{
            marginTop: "20px",
            paddingTop: "14px",
            borderTop: "1px solid var(--border)",
            fontSize: "12px",
            color: "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <FileText size={14} />
          <span>Northfield Student Academic Policy Handbook (Edition 5.0)</span>
        </div>
      </div>
    </div>
  );
};
