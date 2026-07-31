(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { actions, api, chatbot, context, dom, state, utils, viewer } = VLearn;

  async function loadHealth() {
    chatbot.setConnectionStatus("checking");
    try {
      await api.getHealth();
      chatbot.setConnectionStatus("connected");
      return true;
    } catch (error) {
      state.errorState = error;
      chatbot.setConnectionStatus("disconnected");
      return false;
    }
  }

  async function loadLibrary() {
    try {
      const library = await api.getLibrary();
      state.libraryDays = Array.isArray(library.days) ? library.days : [];
      state.allSlides = Array.isArray(library.slides) ? library.slides : [];
      dom.slideCount.textContent = String(state.allSlides.length);
      dom.transcriptCount.textContent = String((library.transcripts || []).length);
      viewer.renderDays(state.libraryDays, dom.librarySearch.value);

      const selected = state.currentDocument
        && state.allSlides.find((slide) => slide.filename === state.currentDocument.filename);
      if (selected) {
        viewer.openDocument(selected, state.currentPage, {
          enableContext: state.slideContextEnabled,
        });
      } else if (state.allSlides.length) {
        viewer.openDocument(state.allSlides[0], 1, { enableContext: false });
      } else {
        viewer.renderEmptyViewer("Chưa có slide trong thư viện bài học.");
      }
      return true;
    } catch (error) {
      state.errorState = error;
      dom.dayList.innerHTML =
        `<div class="empty-state">Chưa kết nối được thư viện bài giảng. Hãy chạy server rồi thử lại.</div>`;
      viewer.renderEmptyViewer(
        "Chưa kết nối được tới thư viện. Giao diện vẫn sẵn sàng và trợ lý sẽ báo khi chức năng cần server."
      );
      return false;
    }
  }

  async function refreshRuntime({ announce = false } = {}) {
    dom.refreshAppBtn.disabled = true;
    const [healthReady, libraryReady] = await Promise.all([loadHealth(), loadLibrary()]);
    dom.refreshAppBtn.disabled = false;
    if (announce) {
      utils.showToast(
        healthReady && libraryReady
          ? "Đã kết nối lại VLearn"
          : "Một số chức năng vẫn chưa kết nối"
      );
    }
  }

  function handleChatClick(event) {
    const suggestion = event.target.closest("[data-suggestion]");
    if (suggestion) {
      const text = suggestion.dataset.suggestion || "";
      if (text && !state.activeRequest) chatbot.askQuestion(text);
      return;
    }

    const retry = event.target.closest("[data-retry-input]");
    if (retry) {
      const text = retry.dataset.retryInput || "";
      if (text && !state.activeRequest) chatbot.askQuestion(text);
      return;
    }

    const actionButton = event.target.closest("[data-source-action]");
    if (actionButton) actions.handleSourceAction(actionButton);
  }

  function bindViewerEvents() {
    dom.toggleLibraryBtn.addEventListener("click", () => {
      document.body.classList.toggle("left-collapsed");
      window.requestAnimationFrame(viewer.applyZoom);
    });
    dom.previousDocBtn.addEventListener("click", () => viewer.openAdjacentDocument(-1));
    dom.goFirstDocBtn.addEventListener("click", () => {
      if (state.allSlides.length) {
        viewer.openDocument(state.allSlides[0], 1, { enableContext: state.slideContextEnabled });
      }
    });
    dom.readModeBtn.addEventListener("click", () => viewer.setMode("read"));
    dom.focusModeBtn.addEventListener("click", () => viewer.setMode("focus"));
    dom.zoomOutBtn.addEventListener("click", () => viewer.setZoom(state.zoom - 0.1));
    dom.zoomInBtn.addEventListener("click", () => viewer.setZoom(state.zoom + 0.1));
    dom.fitWidthBtn.addEventListener("click", () => viewer.setZoom(1));
    dom.prevPageBtn.addEventListener("click", () => viewer.goToPage(state.currentPage - 1));
    dom.nextPageBtn.addEventListener("click", () => viewer.goToPage(state.currentPage + 1));
    dom.pageInput.addEventListener("change", () => {
      viewer.goToPage(Number(dom.pageInput.value || 1));
    });
    dom.pageInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        viewer.goToPage(Number(dom.pageInput.value || 1));
        dom.pageInput.blur();
      }
    });
    dom.librarySearch.addEventListener("input", () => {
      viewer.renderDays(state.libraryDays, dom.librarySearch.value);
    });
    dom.pdfScroll.addEventListener("scroll", () => {
      if (state.scrollSyncFrame) return;
      state.scrollSyncFrame = window.requestAnimationFrame(() => {
        state.scrollSyncFrame = 0;
        viewer.syncPageFromScroll();
      });
    });
    window.addEventListener("resize", viewer.applyZoom);
  }

  function bindChatEvents() {
    dom.assistantFab.addEventListener("click", chatbot.openDrawer);
    dom.closeChatDrawerBtn.addEventListener("click", () => chatbot.closeDrawer());
    dom.refreshAppBtn.addEventListener("click", () => refreshRuntime({ announce: true }));
    dom.chatForm.addEventListener("submit", (event) => {
      event.preventDefault();
      chatbot.askQuestion(dom.chatInput.value);
    });
    dom.chatInput.addEventListener("input", chatbot.updateComposerState);
    dom.chatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.repeat) {
        event.preventDefault();
        if (!dom.sendBtn.disabled) dom.chatForm.requestSubmit();
      }
    });
    dom.chatMessages.addEventListener("click", handleChatClick);
    dom.chatMessages.addEventListener("scroll", () => {
      state.chatScrollPosition = dom.chatMessages.scrollTop;
      if (utils.isNearBottom(dom.chatMessages)) dom.newMessageJump.hidden = true;
    });
    dom.newMessageJump.addEventListener("click", () => {
      dom.chatMessages.scrollTo({ top: dom.chatMessages.scrollHeight, behavior: "smooth" });
      dom.newMessageJump.hidden = true;
    });
    dom.contextSelect.addEventListener("change", () => {
      context.selectContext(dom.contextSelect.value);
    });
    dom.clearSlideContextBtn.addEventListener("click", context.clearSlideContext);
  }

  function bindOverlayEvents() {
    dom.closeTranscriptBtn.addEventListener("click", actions.closeTranscriptViewer);
    dom.transcriptOverlay.addEventListener("click", (event) => {
      if (event.target === dom.transcriptOverlay) actions.closeTranscriptViewer();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (dom.transcriptOverlay.classList.contains("open")) {
        actions.closeTranscriptViewer();
      } else if (state.isChatOpen) {
        chatbot.closeDrawer();
      }
    });
  }

  async function initialize() {
    if (state.initialized) return;
    state.initialized = true;
    bindViewerEvents();
    bindChatEvents();
    bindOverlayEvents();
    context.updateContextUi();
    chatbot.updateComposerState();
    chatbot.showFirstVisitNudge();
    await refreshRuntime();
  }

  VLearn.app = Object.freeze({ initialize, refreshRuntime });
  initialize();
})();
