(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { config, dom, state, utils } = VLearn;

  function sourceIdentity(source) {
    if (source?.source_type === "transcript" || source?.type === "transcript") {
      return source.source_id || source.segment_id || "";
    }
    return source?.source_id || `${source?.file || ""}#page=${Number(source?.page || 0)}`;
  }

  function slidePartsFromSourceId(sourceId) {
    const match = String(sourceId || "").match(/^([^/\\]+\.pdf)#page=(\d+)$/i);
    return match ? { filename: match[1], page: Number(match[2]) } : null;
  }

  function normalizeSource(result) {
    const sourceType = result?.source_type || result?.type || "slide";
    if (sourceType === "transcript") {
      const sourceId = result.source_id || result.segment_id || result.citation || result.source || "";
      return {
        type: "transcript",
        source_type: "transcript",
        source_id: sourceId,
        segment_id: sourceId,
        document_title: result.document_title || result.lesson_title || result.title || "Transcript bài giảng",
        lesson_title: result.lesson_title || result.document_title || result.title || "Transcript bài giảng",
        title: result.title || result.document_title || "Đoạn bài giảng",
        preview: result.preview || "",
        relevance_score: Number(result.relevance_score || result.score || 0),
      };
    }

    const sourceId = result.source_id
      || (result.file && result.page ? `${result.file}#page=${Number(result.page)}` : "");
    const parts = slidePartsFromSourceId(sourceId);
    return {
      type: "slide",
      source_type: "slide",
      source_id: sourceId,
      file: parts?.filename || result.file || "",
      page: parts?.page || Number(result.page || 0),
      document_title: result.document_title || result.lesson_title || result.lesson || "Bài học VLearn",
      lesson_title: result.lesson_title || result.lesson || result.document_title || "Bài học VLearn",
      title: result.title || "Nội dung bài học",
      preview: result.preview || "",
      relevance_score: Number(result.relevance_score || result.score || 0),
    };
  }

  function getValidSources(results) {
    const knownFiles = new Map(
      state.allSlides.map((slide) => [slide.filename, Number(slide.pages) || 0])
    );
    const seen = new Set();
    return (Array.isArray(results) ? results : [])
      .map(normalizeSource)
      .filter((source) => {
        const identity = sourceIdentity(source);
        if (!identity || seen.has(identity)) return false;
        if (source.source_type === "transcript") {
          const valid = /^\[T\d{2}-\d{3}\]$/.test(source.source_id);
          if (valid) seen.add(identity);
          return valid;
        }
        const maxPage = knownFiles.get(source.file);
        const valid = Boolean(
          source.source_id
          && maxPage
          && source.page > 0
          && source.page <= maxPage
        );
        if (valid) seen.add(identity);
        return valid;
      })
      .slice(0, config.maxSources);
  }

  function formatSourceLabel(source, index = null) {
    void index;
    const sourceType = source?.source_type || source?.type;
    if (sourceType === "transcript") {
      const segmentId = source.source_id || source.segment_id || "";
      if (segmentId) return `Đoạn ${segmentId}`;
      return source.document_title || "Transcript bài giảng";
    }
    if (source?.page) return `Slide [${source.page}]`;
    return `${source?.lesson_title || source?.document_title || "Bài học VLearn"}, trang ${source?.page || ""}`;
  }

  function updateContextUi() {
    const label = config.contexts[state.selectedContext] || config.contexts.all;
    dom.contextSelect.value = state.selectedContext;
    dom.contextScopeText.textContent = `Đang tìm trong: ${label}`;
    dom.currentSlideOption.disabled = !state.currentSlide;

    const showPill = Boolean(state.slideContextEnabled && state.currentSlide);
    dom.currentSlidePill.hidden = !showPill;
    if (showPill) {
      dom.currentSlideContextLabel.textContent =
        `Đang hỏi theo: ${state.currentSlide.lesson_title} · Trang ${state.currentSlide.page}`;
    }
    dom.chatInput.placeholder = showPill
      ? "Hỏi về slide đang xem…"
      : "Hỏi kiến thức hoặc tìm một slide…";
  }

  function selectContext(value) {
    const safeValue = Object.hasOwn(config.contexts, value) ? value : "all";
    if (safeValue === "current" && !state.currentSlide) return;
    state.selectedContext = safeValue;
    state.slideContextEnabled = safeValue === "current";
    if (safeValue !== "current") {
      state.selectedBaseContext = safeValue;
    }
    updateContextUi();
  }

  function setCurrentSlide(source, enableContext = true) {
    const normalized = normalizeSource(source);
    if (normalized.source_type !== "slide" || !normalized.source_id) return;
    state.currentSlide = normalized;
    if (enableContext) {
      state.slideContextEnabled = true;
      state.selectedContext = "current";
    }
    updateContextUi();
    VLearn.chatbot?.refreshCurrentCardState();
  }

  function clearSlideContext() {
    state.slideContextEnabled = false;
    state.selectedContext = state.selectedBaseContext || "all";
    updateContextUi();
    utils.showToast("Đã bỏ ngữ cảnh slide cho câu hỏi tiếp theo");
  }

  VLearn.context = Object.freeze({
    sourceIdentity,
    slidePartsFromSourceId,
    normalizeSource,
    getValidSources,
    formatSourceLabel,
    updateContextUi,
    selectContext,
    setCurrentSlide,
    clearSlideContext,
  });
})();
