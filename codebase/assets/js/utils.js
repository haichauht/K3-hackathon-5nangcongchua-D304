(() => {
  "use strict";

  const VLearn = window.VLearn;
  const { dom, state, config } = VLearn;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function removeVietnameseTone(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D");
  }

  function nextMessageId(prefix = "msg") {
    state.messageCounter += 1;
    return `${prefix}-${Date.now()}-${state.messageCounter}`;
  }

  function showToast(message) {
    dom.toast.textContent = message;
    dom.toast.classList.add("show");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(
      () => dom.toast.classList.remove("show"),
      config.toastDurationMs
    );
  }

  function isNearBottom(element, threshold = 90) {
    return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
  }

  function shortPreview(value, maxChars = 180) {
    const compact = String(value || "").replace(/\s+/g, " ").trim();
    if (!compact) return "Mở slide để xem nội dung chi tiết.";
    const sentence = compact.match(/^.{20,180}?[.!?](?:\s|$)/)?.[0]?.trim();
    if (sentence) return sentence;
    const trimmed = compact.slice(0, maxChars);
    const safeEnd = trimmed.lastIndexOf(" ");
    return `${trimmed.slice(0, safeEnd > 80 ? safeEnd : trimmed.length).replace(/[,:;\s]+$/, "")}.`;
  }

  function friendlyError(error, fallback) {
    if (error?.code === "TIMEOUT" || error?.name === "AbortError") {
      return "Yêu cầu mất nhiều thời gian hơn dự kiến. Bạn có thể thử lại.";
    }
    if (error?.code === "INVALID_JSON") {
      return "Hệ thống trả về dữ liệu chưa hợp lệ. Bạn có thể thử lại sau ít phút.";
    }
    if (error?.code === "NETWORK" || window.location.protocol === "file:") {
      return "Chưa kết nối được tới hệ thống tìm kiếm. Giao diện vẫn có thể xem, nhưng chức năng AI hiện chưa hoạt động.";
    }
    return fallback || "Mình chưa xử lý được yêu cầu này. Bạn có thể thử lại.";
  }

  VLearn.utils = Object.freeze({
    escapeHtml,
    removeVietnameseTone,
    nextMessageId,
    showToast,
    isNearBottom,
    shortPreview,
    friendlyError,
  });
})();
