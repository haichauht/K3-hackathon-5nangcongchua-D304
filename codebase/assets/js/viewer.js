(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { api, dom, state, utils } = VLearn;

  function renderDays(days, filter = "") {
    const normalizedFilter = utils.removeVietnameseTone(filter.trim().toLowerCase());
    dom.dayList.innerHTML = "";
    const renderedDays = [];

    days.forEach((day) => {
      const visibleDocs = (day.docs || []).filter((doc) => {
        if (doc.kind !== "slide") return false;
        if (!normalizedFilter) return true;
        return utils.removeVietnameseTone(`${doc.title} ${day.title}`.toLowerCase())
          .includes(normalizedFilter);
      });
      if (visibleDocs.length) renderedDays.push({ day, docs: visibleDocs });
    });

    if (!renderedDays.length) {
      dom.dayList.innerHTML = `<div class="empty-state">Không có bài giảng khớp bộ lọc.</div>`;
      return;
    }

    renderedDays.forEach(({ day, docs }, dayIndex) => {
      const section = document.createElement("section");
      section.className = "day-card";
      section.dataset.dayId = day.id || day.title;
      const isOpen = docs.some((doc) => state.currentDocument?.filename === doc.filename) || dayIndex === 0;
      if (!isOpen) section.classList.add("collapsed");

      const head = document.createElement("button");
      head.type = "button";
      head.className = "day-head";
      head.innerHTML = `
        <div>
          <div class="day-title"><span class="play-dot">▶</span><span>${utils.escapeHtml(day.title)}</span></div>
          <div class="day-meta">${docs.length} tài liệu</div>
        </div>
        <span class="chevron">${isOpen ? "⌃" : "⌄"}</span>
      `;
      head.addEventListener("click", () => {
        section.classList.toggle("collapsed");
        section.querySelector(".chevron").textContent =
          section.classList.contains("collapsed") ? "⌄" : "⌃";
      });

      const docList = document.createElement("div");
      docList.className = "doc-list";
      docs.forEach((doc) => {
        const button = document.createElement("button");
        button.className = "doc-item";
        button.type = "button";
        button.dataset.docId = doc.id;
        button.innerHTML = `
          <span class="doc-kind">PDF slide</span>
          <strong>${utils.escapeHtml(doc.title)}</strong>
          <small>${utils.escapeHtml(doc.subtitle || "")}</small>
        `;
        button.addEventListener("click", () => openDocument(doc, 1, { enableContext: false }));
        docList.appendChild(button);
      });

      section.append(head, docList);
      dom.dayList.appendChild(section);
    });
    updateActiveDocument();
  }

  function sourceForCurrentPage() {
    if (!state.currentDocument) return null;
    return {
      type: "slide",
      source_type: "slide",
      source_id: `${state.currentDocument.filename}#page=${state.currentPage}`,
      file: state.currentDocument.filename,
      page: state.currentPage,
      title: dom.docTitle.textContent || state.currentDocument.title,
      document_title: state.currentDocument.title,
      lesson_title: state.currentDocument.title,
      preview: "",
      relevance_score: 100,
    };
  }

  function openDocument(doc, page = 1, options = {}) {
    if (!doc) return false;
    state.currentDocument = doc;
    state.currentMaxPage = Number(doc.pages) || 1;
    state.currentPage = clampPage(page);
    state.zoom = 1;
    dom.topCourseTitle.textContent = `VLearn · ${doc.title}`;
    dom.docTitle.textContent = doc.title;
    dom.docSubtitle.textContent = doc.subtitle || "Nguồn slide VLearn";
    renderPdfPages();
    updatePageLabels();
    updateActiveDocument();

    const source = sourceForCurrentPage();
    if (options.enableContext) {
      VLearn.context.setCurrentSlide(source, true);
    } else if (state.slideContextEnabled) {
      VLearn.context.setCurrentSlide(source, true);
    } else {
      state.currentSlide = source;
      VLearn.context.updateContextUi();
    }

    window.requestAnimationFrame(() => {
      applyZoom();
      scrollToPage(state.currentPage, false);
    });
    return true;
  }

  function renderPdfPages() {
    if (!state.currentDocument) return;
    dom.pdfScroll.innerHTML = "";
    for (let page = 1; page <= state.currentMaxPage; page += 1) {
      const pageElement = document.createElement("section");
      pageElement.className = "slide-page";
      pageElement.dataset.page = String(page);

      const image = document.createElement("img");
      image.alt = `${state.currentDocument.title} - trang ${page}`;
      image.loading = Math.abs(page - state.currentPage) <= 2 ? "eager" : "lazy";
      const query = `?file=${encodeURIComponent(state.currentDocument.filename)}&page=${page}`;
      image.src = api.url(`${VLearn.config.endpoints.slidePage}${query}`);
      image.onerror = () => {
        pageElement.innerHTML = `<span class="slide-loading">Mình chưa thể hiển thị trang ${page}. Hãy thử tải lại.</span>`;
      };

      pageElement.appendChild(image);
      dom.pdfScroll.appendChild(pageElement);
    }
  }

  function renderEmptyViewer(message) {
    state.currentDocument = null;
    state.currentSlide = null;
    state.currentPage = 1;
    state.currentMaxPage = 1;
    dom.docTitle.textContent = "Chưa có tài liệu";
    dom.docSubtitle.textContent = "Nguồn slide VLearn";
    dom.pdfScroll.innerHTML = `<div class="empty-state">${utils.escapeHtml(message)}</div>`;
    updatePageLabels();
    VLearn.context.updateContextUi();
  }

  function updateActiveDocument() {
    document.querySelectorAll(".doc-item").forEach((item) => {
      item.classList.toggle(
        "active",
        Boolean(state.currentDocument && item.dataset.docId === state.currentDocument.id)
      );
    });
  }

  function updatePageLabels() {
    dom.pageInput.value = String(state.currentPage);
    dom.pageInput.max = String(state.currentMaxPage);
    dom.pageTotal.textContent = `/ ${state.currentMaxPage}`;
    dom.pageCounter.textContent = `Trang ${state.currentPage} / ${state.currentMaxPage}`;
    dom.prevPageBtn.disabled = state.currentPage <= 1 || !state.currentDocument;
    dom.nextPageBtn.disabled = state.currentPage >= state.currentMaxPage || !state.currentDocument;
    document.querySelectorAll(".slide-page").forEach((pageElement) => {
      pageElement.classList.toggle(
        "current",
        Number(pageElement.dataset.page) === state.currentPage
      );
    });
  }

  function clampPage(page) {
    const normalized = Number.isFinite(page) ? Math.round(page) : 1;
    return Math.max(1, Math.min(normalized, state.currentMaxPage));
  }

  function updateCurrentSlideFromViewer() {
    const source = sourceForCurrentPage();
    if (!source) return;
    if (state.slideContextEnabled) {
      VLearn.context.setCurrentSlide(source, true);
    } else {
      state.currentSlide = source;
      VLearn.context.updateContextUi();
      VLearn.chatbot?.refreshCurrentCardState();
    }
  }

  function goToPage(page) {
    if (!state.currentDocument) return;
    state.currentPage = clampPage(page);
    updatePageLabels();
    updateCurrentSlideFromViewer();
    scrollToPage(state.currentPage);
  }

  function scrollToPage(page, smooth = true) {
    const target = dom.pdfScroll.querySelector(`[data-page="${page}"]`);
    if (!target) return;
    state.isProgrammaticScroll = true;
    target.scrollIntoView({
      behavior: smooth ? "smooth" : "auto",
      block: "start",
      inline: "center",
    });
    state.currentPage = clampPage(page);
    updatePageLabels();
    window.setTimeout(() => {
      state.isProgrammaticScroll = false;
    }, smooth ? 420 : 80);
  }

  function syncPageFromScroll() {
    if (!state.currentDocument || state.isProgrammaticScroll) return;
    const pages = Array.from(dom.pdfScroll.querySelectorAll(".slide-page"));
    if (!pages.length) return;
    const containerTop = dom.pdfScroll.getBoundingClientRect().top;
    const anchorY = containerTop + Math.min(220, dom.pdfScroll.clientHeight * 0.34);
    let bestPage = state.currentPage;
    let bestDistance = Number.POSITIVE_INFINITY;

    pages.forEach((pageElement) => {
      const distance = Math.abs(pageElement.getBoundingClientRect().top - anchorY);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestPage = Number(pageElement.dataset.page || state.currentPage);
      }
    });
    if (bestPage !== state.currentPage) {
      state.currentPage = clampPage(bestPage);
      updatePageLabels();
      updateCurrentSlideFromViewer();
    }
  }

  function setZoom(nextZoom) {
    state.zoom = Math.max(0.6, Math.min(1.8, Math.round(nextZoom * 10) / 10));
    applyZoom();
  }

  function applyZoom() {
    const available = Math.max(420, dom.pdfScroll.clientWidth - 56);
    const width = Math.round(available * state.zoom);
    document.querySelectorAll(".slide-page").forEach((pageElement) => {
      pageElement.style.width = `${width}px`;
    });
    dom.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function setMode(mode) {
    const focus = mode === "focus";
    dom.readModeBtn.classList.toggle("active", !focus);
    dom.focusModeBtn.classList.toggle("active", focus);
    document.body.classList.toggle("left-collapsed", focus);
    utils.showToast(focus ? "Đang ở chế độ tập trung" : "Đang ở chế độ đọc");
    window.requestAnimationFrame(applyZoom);
  }

  function openAdjacentDocument(direction) {
    if (!state.allSlides.length) return;
    const currentIndex = Math.max(
      0,
      state.allSlides.findIndex((slide) => slide.filename === state.currentDocument?.filename)
    );
    const nextIndex = (currentIndex + direction + state.allSlides.length) % state.allSlides.length;
    openDocument(state.allSlides[nextIndex], 1, { enableContext: state.slideContextEnabled });
  }

  function openSlideSource(source) {
    const parts = VLearn.context.slidePartsFromSourceId(source?.source_id);
    if (!parts) return null;
    const doc = state.allSlides.find((item) => item.filename === parts.filename);
    if (!doc || parts.page < 1 || parts.page > Number(doc.pages || 0)) return null;
    if (!openDocument(doc, parts.page, { enableContext: true })) return null;
    return sourceForCurrentPage();
  }

  VLearn.viewer = Object.freeze({
    renderDays,
    openDocument,
    renderEmptyViewer,
    updateActiveDocument,
    updatePageLabels,
    goToPage,
    scrollToPage,
    syncPageFromScroll,
    setZoom,
    applyZoom,
    setMode,
    openAdjacentDocument,
    openSlideSource,
    sourceForCurrentPage,
  });
})();
