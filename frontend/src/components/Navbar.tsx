"use client";

import React from "react";
import { Moon, Sun, MessageSquare, BarChart2 } from "lucide-react";
import { DocumentInfo, HealthInfo } from "@/lib/types";

interface NavbarProps {
  activeTab: "chat" | "eval";
  onTabChange: (tab: "chat" | "eval") => void;
  health: HealthInfo | null;
  docInfo: DocumentInfo | null;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  health,
  docInfo,
  theme,
  onToggleTheme,
}) => {
  const isHealthy = health?.status === "healthy";

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        backgroundColor: "var(--bg)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div
        style={{
          maxWidth: "1120px",
          margin: "0 auto",
          padding: "14px 20px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
        }}
      >
        {/* Brand identity — Qurova wordmark + quiet subtitle */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
          <span
            style={{
              fontFamily: "var(--font-heading)",
              fontSize: "1.2rem",
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: "var(--text-primary)",
            }}
          >
            Morpho-RAG
          </span>
          <span
            style={{
              fontSize: "13px",
              color: "var(--text-muted)",
              display: "none",
            }}
            className="header-sub-desktop"
          >
            Northfield academic policy assistant
          </span>
        </div>

        {/* Center navigation tabs — active nav uses var(--accent) indicator */}
        <nav
          style={{
            display: "flex",
            alignItems: "center",
            gap: "4px",
            backgroundColor: "var(--surface-1)",
            padding: "3px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border)",
          }}
        >
          <button
            onClick={() => onTabChange("chat")}
            type="button"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 14px",
              borderRadius: "6px",
              border: "none",
              fontSize: "13px",
              fontWeight: activeTab === "chat" ? 500 : 400,
              color: activeTab === "chat" ? "var(--accent)" : "var(--text-secondary)",
              backgroundColor: activeTab === "chat" ? "var(--surface-2)" : "transparent",
              cursor: "pointer",
              transition: "color 0.15s ease",
            }}
          >
            <MessageSquare size={14} />
            <span>Policy chat</span>
          </button>

          <button
            onClick={() => onTabChange("eval")}
            type="button"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 14px",
              borderRadius: "6px",
              border: "none",
              fontSize: "13px",
              fontWeight: activeTab === "eval" ? 500 : 400,
              color: activeTab === "eval" ? "var(--accent)" : "var(--text-secondary)",
              backgroundColor: activeTab === "eval" ? "var(--surface-2)" : "transparent",
              cursor: "pointer",
              transition: "color 0.15s ease",
            }}
          >
            <BarChart2 size={14} />
            <span>Evaluation benchmarks</span>
          </button>
        </nav>

        {/* Right status & theme toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {/* Subtle status indicator */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
              color: "var(--text-muted)",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: isHealthy ? "var(--positive)" : "var(--danger)",
                display: "inline-block",
              }}
            />
            <span className="tabular-nums">
              {docInfo?.edition ? `Edition ${docInfo.edition}` : "Edition 5.0"}
            </span>
          </div>

          {/* Theme toggle button */}
          <button
            onClick={onToggleTheme}
            aria-label="Toggle theme"
            type="button"
            style={{
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "6px",
              color: "var(--text-muted)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </div>
    </header>
  );
};
