"use client";

import React, { useEffect, useRef, useState } from "react";
import { ArrowUp, StopCircle } from "lucide-react";
import { ChatMessage, Citation, DocumentInfo, HealthInfo, RetrievedChunk } from "@/lib/types";
import { fetchDocumentInfo, fetchHealth, streamChat } from "@/lib/api";
import { Navbar } from "@/components/Navbar";
import { StarterChips } from "@/components/StarterChips";
import { ChatMessageItem } from "@/components/ChatMessageItem";
import { CitationDrawer } from "@/components/CitationDrawer";
import { EvalDashboard } from "@/components/EvalDashboard";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"chat" | "eval">("chat");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [docInfo, setDocInfo] = useState<DocumentInfo | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  // Chat state: casual modern AI chat (ChatGPT/Claude style)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome-msg",
      role: "assistant",
      content:
        "**Northfield Institute of Technology academic policy assistant (Edition 5.0).**\n\nAsk any question regarding attendance requirements, examination policies, re-evaluation fees, or academic standing. Every response is strictly grounded in official handbook text with clickable citation references.",
      timestamp: "just now",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Theme synchronization
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  // Poll backend health & doc info on mount
  useEffect(() => {
    const initBackend = async () => {
      try {
        const [hData, dData] = await Promise.all([
          fetchHealth().catch((err) => {
            console.warn("Backend health ping failed:", err);
            return null;
          }),
          fetchDocumentInfo().catch((err) => {
            console.warn("Doc info ping failed:", err);
            return null;
          }),
        ]);

        if (hData) setHealth(hData);
        if (dData) setDocInfo(dData);

        if (!hData) {
          setBackendError(
            "Backend connection unavailable at http://localhost:8000. Ensure 'backend/main.py' is running."
          );
        } else {
          setBackendError(null);
        }
      } catch (err: unknown) {
        setBackendError(err instanceof Error ? err.message : "Backend connection error");
      }
    };

    initBackend();
  }, []);

  // Auto-scroll messages
  useEffect(() => {
    if (activeTab === "chat") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, activeTab]);

  const handleSend = async (queryText?: string) => {
    const text = (queryText || inputValue).trim();
    if (!text || isGenerating) return;

    setInputValue("");
    setBackendError(null);

    const userMessageId = `user-${Date.now()}`;
    const assistantMessageId = `assistant-${Date.now()}`;
    const nowTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }).toLowerCase();

    // Add user message & placeholder assistant message
    const newUserMsg: ChatMessage = {
      id: userMessageId,
      role: "user",
      content: text,
      timestamp: nowTime,
    };

    const newAssistantMsg: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      status: "searching policy handbook…",
      isStreaming: true,
      timestamp: nowTime,
      retrievedChunks: [],
      citations: [],
    };

    setMessages((prev) => [...prev, newUserMsg, newAssistantMsg]);
    setIsGenerating(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      let accumulatedAnswer = "";
      let retrievedContext: RetrievedChunk[] = [];
      let finalCitations: Citation[] = [];

      await streamChat(
        text,
        5,
        {
          onStatus: (stage, message) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, status: message?.toLowerCase() || stage.toLowerCase() }
                  : msg
              )
            );
          },
          onRetrieved: (chunks) => {
            retrievedContext = chunks;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, retrievedChunks: chunks }
                  : msg
              )
            );
          },
          onToken: (token) => {
            accumulatedAnswer += token;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: accumulatedAnswer,
                      status: "synthesizing grounded answer…",
                    }
                  : msg
              )
            );
          },
          onCitations: (citations) => {
            finalCitations = citations;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, citations }
                  : msg
              )
            );
          },
          onDone: (refusal, modelUsed, fullAnswer) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: fullAnswer || accumulatedAnswer,
                      refusal,
                      modelUsed,
                      citations: finalCitations,
                      retrievedChunks: retrievedContext,
                      isStreaming: false,
                      status: undefined,
                    }
                  : msg
              )
            );
          },
          onError: (err) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content:
                        accumulatedAnswer ||
                        `An error occurred during generation: ${err.message}. Please check if the FastAPI server is running on localhost:8000.`,
                      isStreaming: false,
                      status: undefined,
                    }
                  : msg
              )
            );
          },
        },
        abortController.signal
      );
    } catch (err: unknown) {
      if (!abortController.signal.aborted) {
        setBackendError(err instanceof Error ? err.message : "Error streaming response");
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsGenerating(false);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.isStreaming ? { ...msg, isStreaming: false, status: undefined } : msg
        )
      );
    }
  };

  const handleClearHistory = () => {
    setMessages([
      {
        id: "welcome-msg",
        role: "assistant",
        content:
          "**Northfield Institute of Technology academic policy assistant (Edition 5.0).**\n\nConversation reset. You can ask a new question or pick from the suggested policy inquiries below.",
        timestamp: "just now",
      },
    ]);
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", backgroundColor: "var(--bg)" }}>
      {/* Header bar */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        health={health}
        docInfo={docInfo}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Backend connection notice (if down) */}
      {backendError && (
        <div
          style={{
            backgroundColor: "rgba(244, 63, 94, 0.08)",
            borderBottom: "1px solid rgba(244, 63, 94, 0.22)",
            padding: "8px 20px",
            fontSize: "13px",
            color: "var(--danger)",
            textAlign: "center",
          }}
        >
          {backendError}
        </div>
      )}

      {/* Main content */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {activeTab === "eval" ? (
          <EvalDashboard />
        ) : (
          <div
            style={{
              flex: 1,
              maxWidth: "840px",
              width: "100%",
              margin: "0 auto",
              padding: "32px 20px 140px",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Conversation list — conversation is the interface */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              {messages.map((message) => (
                <ChatMessageItem
                  key={message.id}
                  message={message}
                  onSelectCitation={setSelectedCitation}
                  onSelectQuery={(q) => handleSend(q)}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Starter chips when conversation is at beginning */}
            {messages.length <= 2 && (
              <StarterChips
                onSelectQuery={(q) => handleSend(q)}
                disabled={isGenerating}
              />
            )}
          </div>
        )}
      </main>

      {/* Fixed bottom input bar (Chat tab only) — casual modern AI chat */}
      {activeTab === "chat" && (
        <div
          style={{
            position: "fixed",
            bottom: 0,
            left: 0,
            right: 0,
            backgroundColor: "var(--bg)",
            borderTop: "1px solid var(--border)",
            padding: "16px 20px 18px",
            zIndex: 40,
          }}
        >
          <div
            style={{
              maxWidth: "840px",
              margin: "0 auto",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            {/* Input pill */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                backgroundColor: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "8px 10px 8px 16px",
                transition: "border-color 0.15s ease",
              }}
            >
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Ask about attendance, grading, fees…"
                disabled={isGenerating}
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "var(--text-primary)",
                  fontSize: "15px",
                  fontFamily: "var(--font-sans)",
                }}
              />

              {isGenerating ? (
                <button
                  type="button"
                  onClick={handleStop}
                  title="Stop generation"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "transparent",
                    border: "1px solid var(--border)",
                    color: "var(--danger)",
                    fontSize: "12px",
                    cursor: "pointer",
                  }}
                >
                  <StopCircle size={14} />
                  <span>stop</span>
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!inputValue.trim()}
                  aria-label="Send query"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "32px",
                    height: "32px",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: inputValue.trim() ? "var(--accent)" : "transparent",
                    border: inputValue.trim() ? "none" : "1px solid var(--border)",
                    color: inputValue.trim() ? "#0B0E14" : "var(--text-muted)",
                    cursor: inputValue.trim() ? "pointer" : "default",
                    transition: "background-color 0.15s ease",
                  }}
                >
                  <ArrowUp size={16} />
                </button>
              )}
            </form>

            {/* Input footer meta */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 4px",
                fontSize: "12px",
                color: "var(--text-muted)",
              }}
            >
              <span>Northfield Student Academic Policy Handbook (Edition 5.0)</span>

              {messages.length > 1 && (
                <button
                  type="button"
                  onClick={handleClearHistory}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-muted)",
                    fontSize: "12px",
                    cursor: "pointer",
                    textDecoration: "underline",
                    textUnderlineOffset: "3px",
                  }}
                >
                  clear chat
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Right-side citation drawer (420px) */}
      <CitationDrawer
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
      />
    </div>
  );
}
