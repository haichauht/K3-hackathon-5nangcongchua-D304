(() => {
  "use strict";

  const VLearn = window.VLearn = window.VLearn || {};
  const isFileProtocol = window.location.protocol === "file:";
  const API_BASE_URL = isFileProtocol ? "http://127.0.0.1:8011" : "";

  VLearn.config = Object.freeze({
    API_BASE_URL,
    endpoints: Object.freeze({
      health: "/api/health",
      library: "/api/library",
      recallSearch: "/api/recall-search",
      transcriptSegment: "/api/transcript-segment",
      slidePage: "/api/slide-page",
      slides: "/data/slides",
    }),
    recallTimeoutMs: 170000,
    defaultTimeoutMs: 12000,
    toastDurationMs: 2200,
    assistantNudgeMs: 5200,
    maxSources: 3,
    maxHistoryItems: 8,
    contexts: Object.freeze({
      all: "Tất cả học liệu",
      day01: "Day 1 – AI & LLM Foundation",
      day02: "Day 2 – Xác định bài toán cho AI",
      current: "Slide đang mở",
    }),
  });
})();
