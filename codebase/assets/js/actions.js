(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { api, chatbot, context, dom, state, utils, viewer } = VLearn;

  function sourcesForMessage(messageId, includeTranscripts = false) {
    const message = state.conversationMessages.find((item) => item.id === messageId);
    const sources = includeTranscripts ? message?.citations : message?.slides;
    return Array.isArray(sources) ? sources : [];
  }

  function setActionStatus(messageId, actionKey, value) {
    const current = state.actionStatusByMessage.get(messageId) || {};
    state.actionStatusByMessage.set(messageId, { ...current, [actionKey]: value });
  }

  function messageForId(messageId) {
    return state.conversationMessages.find((item) => item.id === messageId);
  }

  function actionInsertionAnchor(messageId) {
    const message = messageForId(messageId);
    const resultIds = Object.values(message?.actionResults || {});
    for (let index = resultIds.length - 1; index >= 0; index -= 1) {
      if (document.getElementById(resultIds[index])) return resultIds[index];
    }
    return messageId;
  }

  function setButtonBusy(button, busy) {
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
    const card = button.closest("[data-source-card]");
    card?.classList.toggle("is-loading", busy);
  }

  function showInlineCitationError(button, message) {
    const container = button.closest(".msg");
    const target = container?.querySelector("[data-citation-error]");
    if (target) {
      target.textContent = message;
      target.hidden = false;
    } else {
      utils.showToast(message);
    }
  }

  async function openTranscriptSegment(segmentId) {
    if (!/^\[T\d{2}-\d{3}\]$/.test(segmentId)) return false;
    dom.transcriptTitle.textContent = "Đang tải đoạn bài giảng…";
    dom.transcriptMeta.textContent = "Nguồn học liệu VLearn";
    dom.transcriptContent.textContent = "Đang mở đúng đoạn được trích dẫn…";
    dom.transcriptOverlay.classList.add("open");
    try {
      const payload = await api.getTranscriptSegment(segmentId);
      dom.transcriptTitle.textContent = payload.document_title || "Đoạn bài giảng";
      dom.transcriptMeta.textContent = payload.truncated
        ? "Đoạn trích đã được rút gọn"
        : "Đoạn trích từ bài giảng";
      dom.transcriptContent.textContent =
        payload.content || "Đoạn bài giảng này chưa có nội dung hiển thị.";
      return true;
    } catch (error) {
      dom.transcriptTitle.textContent = "Chưa mở được đoạn bài giảng";
      dom.transcriptContent.textContent = utils.friendlyError(
        error,
        "Mình chưa thể mở đoạn bài giảng này. Bạn có thể thử lại."
      );
      return false;
    }
  }

  function closeTranscriptViewer() {
    dom.transcriptOverlay.classList.remove("open");
    dom.transcriptContent.textContent = "";
  }

  async function openSource(source) {
    if (source?.source_type === "transcript") {
      return openTranscriptSegment(source.source_id);
    }
    return viewer.openSlideSource(source);
  }

  async function handleOpen(button, source, messageId) {
    if (!source) {
      showInlineCitationError(button, "Citation này không còn nguồn hợp lệ để mở.");
      return;
    }
    const sourceId = context.sourceIdentity(source);
    const currentViewerSourceId = context.sourceIdentity(viewer.sourceForCurrentPage());
    if (source.source_type === "slide" && sourceId === currentViewerSourceId) {
      chatbot.closeDrawer();
      return;
    }

    setButtonBusy(button, true);
    state.openSlideStatus = { messageId, sourceId, status: "loading" };
    const openedSource = await openSource(source);
    const openedSourceId = source.source_type === "slide"
      ? context.sourceIdentity(openedSource)
      : sourceId;
    const opened = Boolean(openedSource) && openedSourceId === sourceId;
    state.openSlideStatus = { messageId, sourceId, status: opened ? "success" : "error" };
    setButtonBusy(button, false);

    if (!opened) {
      showInlineCitationError(
        button,
        "Mình chưa thể mở trang slide này. Bạn có thể thử lại hoặc chọn nguồn khác."
      );
      return;
    }

    state.selectedSource = source.source_type === "slide" ? openedSource : source;
    if (source.source_type === "slide") {
      chatbot.refreshCurrentCardState();
      chatbot.closeDrawer();
    }
  }

  function actionDefinition(action) {
    const definitions = {
      summarize: {
        apiAction: "summarize",
        prompt: "Tóm tắt slide đã chọn",
        loading: "Đang tóm tắt slide đã chọn…",
      },
      synthesize: {
        apiAction: "synthesize",
        prompt: "Tóm tắt tất cả slide liên quan",
        loading: "Đang tổng hợp các slide liên quan…",
      },
      self_check: {
        apiAction: "self_check",
        prompt: "Tạo câu hỏi tự kiểm tra từ các slide đã chọn",
        loading: "Đang tạo câu hỏi tự kiểm tra…",
      },
      reveal_answers: {
        apiAction: "synthesize",
        prompt: "Trả lời ngắn gọn các câu tự kiểm tra dựa trên nguồn đã chọn",
        loading: "Đang chuẩn bị đáp án có trích dẫn…",
      },
    };
    return definitions[action] || null;
  }

  async function runLearningAction(button, action, messageId, sourceIndex) {
    const definition = actionDefinition(action);
    if (!definition) return;
    const messageSources = sourcesForMessage(messageId);
    const sources = action === "summarize"
      ? [messageSources[sourceIndex]].filter(Boolean)
      : messageSources.slice(0, VLearn.config.maxSources);
    if (!sources.length) {
      showInlineCitationError(button, "Kết quả này không còn nguồn hợp lệ để thực hiện thao tác.");
      return;
    }

    const actionKey = `${action}:${Number.isFinite(sourceIndex) ? sourceIndex : "group"}`;
    const existing = state.actionStatusByMessage.get(messageId)?.[actionKey];
    if (existing?.status === "loading") return;
    if (existing?.status === "success") {
      utils.showToast("Kết quả của thao tác này đã có ở bên dưới.");
      return;
    }

    const requestId = `action-${++state.requestCounter}`;
    const resultMessageId = utils.nextMessageId("bot");
    setActionStatus(messageId, actionKey, {
      status: "loading",
      requestId,
      resultMessageId,
    });
    const parentMessage = messageForId(messageId);
    if (parentMessage) {
      parentMessage.actionResults = parentMessage.actionResults || {};
      parentMessage.actionResults[actionKey] = resultMessageId;
    }
    setButtonBusy(button, true);
    const loading = chatbot.createLoadingMessage(definition.loading, {
      id: resultMessageId,
      afterMessageId: actionInsertionAnchor(messageId),
      preserveScroll: true,
      meta: { requestId },
    });

    try {
      const payload = await api.searchRecall(definition.prompt, {
        requestId,
        sources,
        action: definition.apiAction,
      });
      const activeAction = state.actionStatusByMessage.get(messageId)?.[actionKey];
      if (
        activeAction?.requestId !== requestId
        || (payload.request_id && payload.request_id !== requestId)
      ) {
        return;
      }
      chatbot.renderActionResult(loading, payload, {
        action,
        requestId,
        sources,
        sourceMessageId: messageId,
      });
      setActionStatus(messageId, actionKey, {
        status: "success",
        requestId,
        resultMessageId,
      });
      chatbot.setConnectionStatus("connected");
    } catch (error) {
      const activeAction = state.actionStatusByMessage.get(messageId)?.[actionKey];
      if (activeAction?.requestId !== requestId) return;
      chatbot.renderError(
        loading,
        utils.friendlyError(error, "Mình chưa hoàn thành được thao tác này. Bạn có thể thử lại."),
        "",
        { action }
      );
      setActionStatus(messageId, actionKey, {
        status: "error",
        requestId,
        resultMessageId,
      });
      chatbot.setConnectionStatus("disconnected");
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function handleSourceAction(button) {
    if (button.disabled) return;
    const action = button.dataset.sourceAction;
    const messageId = button.dataset.messageId || "";
    const sourceIndex = button.dataset.sourceIndex === undefined
      ? Number.NaN
      : Number(button.dataset.sourceIndex);

    if (action === "show_sources") {
      const sourceMap = document.querySelector(`[data-source-map="${messageId}"]`);
      if (sourceMap) {
        sourceMap.hidden = false;
        button.hidden = true;
      }
      return;
    }

    if (action === "open") {
      const source = sourcesForMessage(messageId)[sourceIndex];
      await handleOpen(button, source, messageId);
      return;
    }

    if (action === "citation") {
      const source = sourcesForMessage(messageId, true)[sourceIndex];
      await handleOpen(button, source, messageId);
      return;
    }

    await runLearningAction(button, action, messageId, sourceIndex);
  }

  VLearn.actions = Object.freeze({
    handleSourceAction,
    openTranscriptSegment,
    closeTranscriptViewer,
  });
})();
