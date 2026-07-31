(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { api, config, context, dom, state, utils } = VLearn;

  function setConnectionStatus(status) {
    const labels = {
      checking: "Đang kiểm tra",
      connected: "Đã kết nối",
      disconnected: "Chưa kết nối",
    };
    state.connectionStatus = labels[status] ? status : "disconnected";
    dom.connectionStatus.dataset.status = state.connectionStatus;
    dom.connectionStatus.textContent = labels[state.connectionStatus];
  }

  function setUnread(hasUnread) {
    state.hasUnreadMessage = Boolean(hasUnread);
    dom.assistantUnread.hidden = !state.hasUnreadMessage;
    dom.assistantFab.setAttribute(
      "aria-label",
      state.hasUnreadMessage
        ? "Mở trợ lý VLearn Recall, có kết quả mới"
        : "Mở trợ lý VLearn Recall"
    );
  }

  function openDrawer() {
    state.isChatOpen = true;
    document.body.classList.add("chat-open");
    dom.chatDrawer.classList.add("open");
    dom.chatDrawer.setAttribute("aria-hidden", "false");
    dom.assistantFab.setAttribute("aria-expanded", "true");
    setUnread(false);
    dom.newMessageJump.hidden = true;
    dom.assistantNudge.hidden = true;
    window.requestAnimationFrame(() => {
      dom.chatMessages.scrollTop = state.chatScrollPosition;
      dom.chatInput.focus();
    });
  }

  function closeDrawer({ restoreFocus = true } = {}) {
    if (!state.isChatOpen) return;
    state.chatScrollPosition = dom.chatMessages.scrollTop;
    state.isChatOpen = false;
    document.body.classList.remove("chat-open");
    dom.chatDrawer.classList.remove("open");
    dom.chatDrawer.setAttribute("aria-hidden", "true");
    dom.assistantFab.setAttribute("aria-expanded", "false");
    if (restoreFocus) dom.assistantFab.focus();
  }

  function showFirstVisitNudge() {
    try {
      if (window.sessionStorage.getItem("vlearn-recall-nudge-seen")) return;
      window.sessionStorage.setItem("vlearn-recall-nudge-seen", "1");
    } catch {
      // The hint remains non-essential when storage is unavailable.
    }
    dom.assistantNudge.hidden = false;
    window.setTimeout(() => {
      dom.assistantNudge.hidden = true;
    }, config.assistantNudgeMs);
  }

  function updateComposerState() {
    const hasText = Boolean(dom.chatInput.value.trim());
    dom.sendBtn.disabled = !hasText || Boolean(state.activeRequest);
    dom.chatInput.style.height = "auto";
    dom.chatInput.style.height = `${Math.min(dom.chatInput.scrollHeight, 130)}px`;
  }

  function recordMessage(id, role, content, extra = {}) {
    const existing = state.conversationMessages.find((item) => item.id === id);
    if (existing) {
      Object.assign(existing, { role, content, ...extra });
      if (role === "bot") {
        existing.slides = Array.isArray(existing.slides) ? existing.slides : [];
        existing.citations = Array.isArray(existing.citations) ? existing.citations : [];
        existing.actions = Array.isArray(existing.actions) ? existing.actions : [];
        existing.actionResults = existing.actionResults || {};
      }
      return existing;
    }
    const botState = role === "bot"
      ? {
          intent: "",
          status: "",
          slides: [],
          citations: [],
          actions: [],
          actionResults: {},
        }
      : {};
    const message = { id, role, content, createdAt: Date.now(), ...botState, ...extra };
    state.conversationMessages.push(message);
    return message;
  }

  function appendMessage(role, content, options = {}) {
    const messageId = options.id || utils.nextMessageId(role);
    const existingElement = document.getElementById(messageId);
    if (existingElement) return existingElement;
    const wasNearBottom = utils.isNearBottom(dom.chatMessages);
    const previousScrollTop = dom.chatMessages.scrollTop;
    const element = document.createElement(options.tagName || "div");
    element.id = messageId;
    element.dataset.messageId = messageId;
    element.className = `msg ${role === "user" ? "msg-user" : role === "system" ? "msg-system" : "msg-bot"}`;
    element.innerHTML = role === "user" ? utils.escapeHtml(content) : content;

    const anchor = options.afterMessageId
      ? document.getElementById(options.afterMessageId)
      : null;
    if (anchor?.parentNode === dom.chatMessages) {
      anchor.insertAdjacentElement("afterend", element);
    } else {
      dom.chatMessages.appendChild(element);
    }

    recordMessage(messageId, role, options.plainText || content, options.meta);
    if (options.preserveScroll) {
      dom.chatMessages.scrollTop = previousScrollTop;
      window.requestAnimationFrame(() => {
        dom.chatMessages.scrollTop = previousScrollTop;
      });
    }
    if (options.forceScroll || role === "user") {
      element.scrollIntoView({ behavior: "auto", block: "end" });
    } else if (state.isChatOpen && wasNearBottom && !options.preserveScroll) {
      dom.chatMessages.scrollTo({ top: dom.chatMessages.scrollHeight, behavior: "smooth" });
    } else if (state.isChatOpen && !wasNearBottom && role === "bot") {
      dom.newMessageJump.hidden = false;
    }
    if (!state.isChatOpen && role === "bot" && options.markUnread) setUnread(true);
    return element;
  }

  function replaceMessage(element, content, plainText, meta = {}) {
    const preserveScroll = element.dataset.preserveScroll === "true";
    const previousScrollTop = dom.chatMessages.scrollTop;
    element.innerHTML = content;
    element.removeAttribute("aria-busy");
    recordMessage(element.id, "bot", plainText, meta);
    if (preserveScroll) {
      dom.chatMessages.scrollTop = previousScrollTop;
      window.requestAnimationFrame(() => {
        dom.chatMessages.scrollTop = previousScrollTop;
      });
    }
  }

  function createLoadingMessage(label, options = {}) {
    const html = `
      <div class="loading-row" role="status">
        <span class="loading-dot" aria-hidden="true"></span>
        <span>${utils.escapeHtml(label)}</span>
      </div>
    `;
    const element = appendMessage("bot", html, {
      afterMessageId: options.afterMessageId,
      id: options.id,
      forceScroll: options.forceScroll,
      preserveScroll: options.preserveScroll,
      plainText: label,
      meta: options.meta,
    });
    element.setAttribute("aria-busy", "true");
    element.dataset.preserveScroll = String(Boolean(options.preserveScroll));
    return element;
  }

  function detectUiIntent(text) {
    const normalized = utils.removeVietnameseTone(text.toLowerCase());
    if (
      state.currentSlide
      && /(slide nay|trang nay|phan nay|dang mo|dang xem|giai thich|tom tat|y thu|vi du|kiem tra)/.test(normalized)
    ) {
      return "current_slide";
    }
    if (
      /(slide nao|trang nao|o dau|nam o dau|tim.*slide|tim.*trang|phan .* nam|noi dung do duoc noi)/.test(normalized)
    ) {
      return "locate";
    }
    return "knowledge";
  }

  function loadingLabel(intent) {
    if (intent === "locate") return "Đang tìm trong slide và tài liệu bài học…";
    if (intent === "current_slide") return "Đang đọc slide đang mở…";
    return "Đang trả lời câu hỏi từ học liệu của khóa…";
  }

  function renderFieldCitations(citedSources, allSources, messageId) {
    const indexes = (Array.isArray(citedSources) ? citedSources : [])
      .map((source) => allSources.findIndex(
        (candidate) => context.sourceIdentity(candidate) === context.sourceIdentity(source)
      ))
      .filter((index, position, values) => index >= 0 && values.indexOf(index) === position);
    if (!indexes.length) return "";
    return `
      <span class="field-citations" aria-label="Nguồn cho ý này">
        ${indexes.map((index) => `
          <button
            class="citation-link inline-citation"
            type="button"
            data-source-action="citation"
            data-message-id="${utils.escapeHtml(messageId)}"
            data-source-index="${index}"
          >${utils.escapeHtml(context.formatSourceLabel(allSources[index], index))}</button>
        `).join("")}
      </span>
    `;
  }

  function renderStructuredGeneration(generation, sources, messageId, meta = {}) {
    if (!generation || typeof generation !== "object") return "";
    const degraded = meta?.degraded
      ? `<p class="generation-mode-note">Đang dùng chế độ diễn giải offline từ nguồn đã tìm được.</p>`
      : "";
    const sourceLinks = (item) => renderFieldCitations(
      item?.citations || [],
      sources,
      messageId
    );

    if (generation.kind === "slide_summary") {
      const points = Array.isArray(generation.key_points) ? generation.key_points : [];
      if (!generation.title || !generation.main_idea || !generation.takeaway || !points.length) return "";
      return `
        <article class="answer-card structured-answer">
          <h3 class="answer-title">${utils.escapeHtml(generation.title)}</h3>
          ${degraded}
          <section class="structured-section">
            <h4>Ý chính</h4>
            <p>${utils.escapeHtml(generation.main_idea)}</p>
            ${renderFieldCitations(sources, sources, messageId)}
          </section>
          <section class="structured-section">
            <h4>Điều cần nhớ</h4>
            <ol class="structured-list">
              ${points.map((point) => `
                <li>
                  <span>${utils.escapeHtml(point.text)}</span>
                  ${sourceLinks(point)}
                </li>
              `).join("")}
            </ol>
          </section>
          <section class="structured-section">
            <h4>Kết luận</h4>
            <p>${utils.escapeHtml(generation.takeaway)}</p>
          </section>
        </article>
      `;
    }

    if (generation.kind === "multi_slide_synthesis") {
      const themes = Array.isArray(generation.themes) ? generation.themes : [];
      if (!generation.topic || !generation.overview || !generation.connections || !themes.length) return "";
      return `
        <article class="answer-card structured-answer">
          <h3 class="answer-title">${utils.escapeHtml(generation.topic)}</h3>
          ${degraded}
          <div class="answer-body"><p>${utils.escapeHtml(generation.overview)}</p></div>
          <div class="structured-themes">
            ${themes.map((theme) => `
              <section class="structured-section">
                <h4>${utils.escapeHtml(theme.heading)}</h4>
                <p>${utils.escapeHtml(theme.summary)}</p>
                ${sourceLinks(theme)}
              </section>
            `).join("")}
          </div>
          <section class="structured-section connection-section">
            <h4>Mối liên hệ</h4>
            <p>${utils.escapeHtml(generation.connections)}</p>
          </section>
        </article>
      `;
    }

    if (generation.kind === "self_check") {
      const questions = Array.isArray(generation.questions) ? generation.questions : [];
      if (!generation.title || !generation.instructions || !questions.length) return "";
      return `
        <article class="answer-card structured-answer">
          <h3 class="answer-title">${utils.escapeHtml(generation.title)}</h3>
          ${degraded}
          <p class="self-check-note">${utils.escapeHtml(generation.instructions)}</p>
          <ol class="structured-list self-check-list">
            ${questions.map((item) => `
              <li>
                <span>${utils.escapeHtml(item.question)}</span>
                ${sourceLinks(item)}
              </li>
            `).join("")}
          </ol>
        </article>
      `;
    }

    if (generation.kind === "learning_answer") {
      const points = Array.isArray(generation.key_points) ? generation.key_points : [];
      if (!generation.title || !generation.answer || !points.length) return "";
      return `
        <article class="answer-card structured-answer">
          <h3 class="answer-title">${utils.escapeHtml(generation.title)}</h3>
          ${degraded}
          <div class="answer-body"><p>${utils.escapeHtml(generation.answer)}</p></div>
          <ul class="structured-list">
            ${points.map((point) => `
              <li>
                <span>${utils.escapeHtml(point.text)}</span>
                ${sourceLinks(point)}
              </li>
            `).join("")}
          </ul>
        </article>
      `;
    }
    return "";
  }

  function renderSourceCards(sources, messageId, hidden = false) {
    const slides = sources.filter((source) => source.source_type === "slide").slice(0, config.maxSources);
    if (!slides.length) return "";
    const cards = slides.map((source, index) => {
      const currentSourceId = state.currentDocument
        ? `${state.currentDocument.filename}#page=${Number(state.currentPage || 1)}`
        : "";
      const current = context.sourceIdentity(source) === currentSourceId;
      return `
        <article
          class="result-card${current ? " is-current" : ""}"
          data-source-card
          data-source-id="${utils.escapeHtml(source.source_id)}"
        >
          <div class="result-card-label">
            <span>Slide [${source.page}]</span>
            <span class="current-card-label"${current ? "" : " hidden"}>Đang xem</span>
          </div>
          <h4>${utils.escapeHtml(source.title)}</h4>
          <p class="result-preview">${utils.escapeHtml(utils.shortPreview(source.preview))}</p>
          <p class="result-location">${utils.escapeHtml(source.lesson_title)} · Trang ${source.page}</p>
          <div class="result-actions">
            <button
              class="source-link primary"
              type="button"
              data-source-action="open"
              data-message-id="${utils.escapeHtml(messageId)}"
              data-source-index="${index}"
            >Mở slide</button>
            <button
              class="source-link"
              type="button"
              data-source-action="summarize"
              data-message-id="${utils.escapeHtml(messageId)}"
              data-source-index="${index}"
            >Tóm tắt slide này</button>
          </div>
        </article>
      `;
    }).join("");

    return `
      <section class="source-map" data-source-map="${utils.escapeHtml(messageId)}"${hidden ? " hidden" : ""}>
        ${cards}
        <div class="group-actions" aria-label="Hành động với các slide liên quan">
          <button class="group-action primary" type="button" data-source-action="synthesize" data-message-id="${utils.escapeHtml(messageId)}">Tóm tắt tất cả</button>
          <button class="group-action" type="button" data-source-action="self_check" data-message-id="${utils.escapeHtml(messageId)}">Tự kiểm tra</button>
        </div>
      </section>
    `;
  }

  function renderSuggestions(items) {
    const suggestions = (Array.isArray(items) ? items : [])
      .filter((item) => item && (item.input || item.label))
      .slice(0, 3);
    if (!suggestions.length) return "";
    return `
      <div class="follow-ups" aria-label="Gợi ý làm rõ">
        ${suggestions.map((item) => `
          <button class="follow-up-btn" type="button" data-suggestion="${utils.escapeHtml(item.input || item.label)}">
            ${utils.escapeHtml(item.label || item.input)}
          </button>
        `).join("")}
      </div>
    `;
  }

  function renderError(element, message, retryInput, options = {}) {
    const retry = retryInput
      ? `<button class="retry-btn" type="button" data-retry-input="${utils.escapeHtml(retryInput)}">Thử lại</button>`
      : "";
    replaceMessage(
      element,
      `<span class="status-label status-error">Chưa thể hoàn tất</span>
       <div class="answer-body"><p>${utils.escapeHtml(message)}</p></div>
       ${retry}`,
      message,
      options
    );
  }

  function renderRecallResponse(element, payload, request) {
    const status = payload?.status || "NOT_FOUND";
    const sources = context.getValidSources(payload?.results || []);
    const messageId = element.id;

    if (status === "CLARIFY") {
      const message = payload.message
        || "Mình chưa xác định được nội dung bạn muốn tìm. Bạn nhớ thêm một từ khóa, tên chủ đề hoặc buổi học nào không?";
      replaceMessage(
        element,
        `<span class="status-label status-clarify">Mình cần thêm một chút thông tin</span>
         <div class="answer-body"><p>${utils.escapeHtml(message)}</p></div>
         ${renderSuggestions(payload.suggestions)}`,
        message,
        { status }
      );
      return;
    }

    if (status === "NOT_FOUND") {
      const message = "Mình chưa tìm thấy slide đủ phù hợp với nội dung này. Bạn có thể thử thêm một cụm từ từng nghe, tên chủ đề hoặc chọn phạm vi bài học cụ thể hơn.";
      replaceMessage(
        element,
        `<span class="status-label status-not-found">Chưa tìm thấy nội dung phù hợp</span>
         <div class="answer-body"><p>${utils.escapeHtml(message)}</p></div>
         ${renderSuggestions(payload.suggestions)}`,
        message,
        { status }
      );
      return;
    }

    if (status === "AI_UNAVAILABLE" || status === "INVALID_MODEL_OUTPUT") {
      renderError(
        element,
        payload.message || "Tạm thời chưa thể tạo phần tóm tắt. Vui lòng thử lại.",
        request.text,
        { status, error: payload.error }
      );
      return;
    }

    if (status !== "FOUND" || !sources.length) {
      renderError(
        element,
        "Kết quả chưa có nguồn hợp lệ để kiểm chứng. Bạn có thể thử lại với câu hỏi cụ thể hơn.",
        request.text,
        { status: "ERROR" }
      );
      return;
    }

    const slideSources = sources.filter((source) => source.source_type === "slide");
    const isLocate = payload?.intent?.type === "LOCATE_SLIDE" || request.intent === "locate";
    if (isLocate) {
      const lead = payload.message
        || `Mình tìm thấy ${slideSources.length} slide phù hợp nhất với nội dung bạn đang tìm.`;
      replaceMessage(
        element,
        `<div class="answer-body"><p>${utils.escapeHtml(lead)}</p></div>
         ${renderSourceCards(slideSources, messageId)}`,
        lead,
        {
          requestId: request.requestId,
          status,
          intent: "LOCATE_SLIDE",
          slides: slideSources,
          citations: [],
          actions: ["synthesize", "self_check"],
          actionResults: {},
        }
      );
      state.chatHistory.push({ role: "assistant", content: lead, status });
      return;
    }

    const citationSources = context.getValidSources(payload?.citations || []);
    const structuredMarkup = renderStructuredGeneration(
      payload.generation,
      citationSources,
      messageId,
      payload.generation_meta
    );
    if (!structuredMarkup) {
      renderError(
        element,
        "Kết quả AI chưa có đủ trường có cấu trúc để hiển thị an toàn. Vui lòng thử lại.",
        request.text,
        { status: "INVALID_MODEL_OUTPUT" }
      );
      return;
    }
    const findSlidesAction = request.intent === "knowledge" && slideSources.length
      ? `<div class="follow-ups"><button class="follow-up-btn" type="button" data-source-action="show_sources" data-message-id="${utils.escapeHtml(messageId)}">Tìm slide liên quan</button></div>`
      : "";
    const markup = `
      ${structuredMarkup}
      ${findSlidesAction}
      ${renderSourceCards(slideSources, messageId, true)}
    `;
    replaceMessage(element, markup, payload.answer || payload.message || "", {
      requestId: request.requestId,
      status,
      intent: payload?.intent?.type || "KNOWLEDGE_ANSWER",
      slides: slideSources,
      citations: citationSources,
      actions: slideSources.length ? ["show_sources"] : [],
      actionResults: {},
    });
    state.chatHistory.push({
      role: "assistant",
      content: payload.answer || payload.message || "",
      status,
    });
  }

  async function askQuestion(text) {
    const question = String(text || "").trim();
    if (!question || state.activeRequest) return;
    const intent = detectUiIntent(question);
    const requestId = `request-${++state.requestCounter}`;
    state.activeRequest = { id: requestId, text: question, intent };
    state.errorState = null;
    dom.welcomeCard.hidden = true;

    appendMessage("user", question, { forceScroll: true });
    state.chatHistory.push({ role: "user", content: question });
    dom.chatInput.value = "";
    updateComposerState();
    const loading = createLoadingMessage(loadingLabel(intent), {
      preserveScroll: true,
      meta: { requestId },
    });

    try {
      const payload = await api.searchRecall(question, {
        requestId,
        useCurrentSlide: intent === "current_slide",
      });
      if (
        state.activeRequest?.id !== requestId
        || (payload.request_id && payload.request_id !== requestId)
      ) {
        loading.remove();
        state.conversationMessages = state.conversationMessages.filter(
          (message) => message.id !== loading.id
        );
        return;
      }
      renderRecallResponse(loading, payload, { text: question, intent, requestId });
      setConnectionStatus("connected");
      if (!state.isChatOpen) setUnread(true);
    } catch (error) {
      if (state.activeRequest?.id !== requestId) return;
      state.errorState = error;
      setConnectionStatus("disconnected");
      const message = utils.friendlyError(error);
      renderError(loading, message, question, { status: "ERROR" });
      if (!dom.chatInput.value) dom.chatInput.value = question;
      if (!state.isChatOpen) setUnread(true);
    } finally {
      if (state.activeRequest?.id === requestId) state.activeRequest = null;
      updateComposerState();
    }
  }

  function renderActionResult(element, payload, options) {
    if (payload?.status === "AI_UNAVAILABLE" || payload?.status === "INVALID_MODEL_OUTPUT") {
      renderError(
        element,
        payload.message || "Tạm thời chưa thể tạo phần tóm tắt. Vui lòng thử lại.",
        "",
        { action: options.action, status: payload.status }
      );
      return;
    }
    const sources = context.getValidSources(payload?.citations || []);
    if (payload?.status !== "FOUND" || !sources.length || !payload.generation) {
      renderError(
        element,
        payload?.message || "Nguồn này chưa đủ thông tin để hoàn thành thao tác.",
        "",
        { action: options.action }
      );
      return;
    }
    const structuredMarkup = renderStructuredGeneration(
      payload.generation,
      sources,
      element.id,
      payload.generation_meta
    );
    if (!structuredMarkup) {
      renderError(
        element,
        "Kết quả AI chưa có đủ trường có cấu trúc để hiển thị an toàn. Vui lòng thử lại.",
        "",
        { action: options.action, status: "INVALID_MODEL_OUTPUT" }
      );
      return;
    }
    const slides = sources.filter((source) => source.source_type === "slide");
    replaceMessage(
      element,
      structuredMarkup,
      payload.answer || payload.message || "",
      {
        requestId: options.requestId,
        intent: "ACTION_RESULT",
        status: "FOUND",
        action: options.action,
        slides,
        citations: sources,
        actions: [],
        actionResults: {},
      }
    );
    state.chatHistory.push({
      role: "assistant",
      content: payload.answer || payload.message || "",
      status: "FOUND",
    });
    if (!state.isChatOpen) setUnread(true);
  }

  function refreshCurrentCardState() {
    const currentSourceId = state.currentDocument
      ? `${state.currentDocument.filename}#page=${Number(state.currentPage || 1)}`
      : "";
    document.querySelectorAll("[data-source-card]").forEach((card) => {
      const isCurrent = card.dataset.sourceId === currentSourceId;
      card.classList.toggle("is-current", isCurrent);
      const label = card.querySelector(".current-card-label");
      if (label) label.hidden = !isCurrent;
    });
  }

  VLearn.chatbot = Object.freeze({
    setConnectionStatus,
    setUnread,
    openDrawer,
    closeDrawer,
    showFirstVisitNudge,
    updateComposerState,
    appendMessage,
    createLoadingMessage,
    renderActionResult,
    renderError,
    askQuestion,
    refreshCurrentCardState,
  });
})();
