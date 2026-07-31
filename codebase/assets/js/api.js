(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { config, state } = VLearn;

  function url(path) {
    return `${config.API_BASE_URL}${path}`;
  }

  async function requestJson(path, options = {}, timeoutMs = config.defaultTimeoutMs) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      let response;
      try {
        response = await fetch(url(path), { ...options, signal: controller.signal });
      } catch (error) {
        if (error.name === "AbortError") {
          error.code = "TIMEOUT";
        } else {
          error.code = "NETWORK";
        }
        throw error;
      }

      const raw = await response.text();
      let payload = {};
      try {
        payload = raw ? JSON.parse(raw) : {};
      } catch (error) {
        error.code = "INVALID_JSON";
        throw error;
      }

      if (!response.ok) {
        const error = new Error(
          payload.error?.message || payload.message || `HTTP ${response.status}`
        );
        error.code = `HTTP_${response.status}`;
        error.payload = payload;
        throw error;
      }
      return payload;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  function safeSourcePayload(source) {
    return {
      type: source.source_type || source.type,
      source_type: source.source_type || source.type,
      source_id: source.source_id,
      relevance_score: Number(source.relevance_score || 0),
    };
  }

  function getHealth() {
    return requestJson(config.endpoints.health);
  }

  function getLibrary() {
    return requestJson(config.endpoints.library);
  }

  function searchRecall(input, options = {}) {
    const sources = Array.isArray(options.sources)
      ? options.sources.slice(0, config.maxSources).map(safeSourcePayload)
      : [];
    const useCurrentSlide = state.slideContextEnabled || options.useCurrentSlide;
    const currentSlideSourceId = useCurrentSlide
      ? state.currentSlide?.source_id || ""
      : "";

    return requestJson(
      config.endpoints.recallSearch,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: options.requestId || "",
          input,
          history: state.chatHistory.slice(-config.maxHistoryItems),
          previous_sources: sources,
          action: options.action || "",
          scope: options.useCurrentSlide ? "current" : state.selectedContext,
          current_slide_source_id: currentSlideSourceId,
        }),
      },
      config.recallTimeoutMs
    );
  }

  function getTranscriptSegment(segmentId) {
    const query = `?segment_id=${encodeURIComponent(segmentId)}`;
    return requestJson(`${config.endpoints.transcriptSegment}${query}`);
  }

  VLearn.api = Object.freeze({
    url,
    requestJson,
    getHealth,
    getLibrary,
    searchRecall,
    getTranscriptSegment,
  });
})();
