(function () {
  "use strict";

  const config = window.__BI_RMP_DASHBOARD_CONFIG__ || {};
  const coreApiBaseUrl = String(config.coreApiBaseUrl || "http://127.0.0.1:8000").replace(/\/+$/, "");
  const dashboardPrefix = String(config.dashboardApiPrefix || "/api/dashboard");
  const pageSize = 20;

  const state = {
    page: 1,
    businessId: "",
    platform: "",
    total: 0,
    businesses: [],
  };

  const els = {
    connectionStatus: document.getElementById("connectionStatus"),
    apiBaseUrl: document.getElementById("apiBaseUrl"),
    businessFilter: document.getElementById("businessFilter"),
    platformFilter: document.getElementById("platformFilter"),
    refreshButton: document.getElementById("refreshButton"),
    resetButton: document.getElementById("resetButton"),
    metricTotalItems: document.getElementById("metricTotalItems"),
    metricReviews: document.getElementById("metricReviews"),
    metricAnalyzed: document.getElementById("metricAnalyzed"),
    metricRisk: document.getElementById("metricRisk"),
    resultMeta: document.getElementById("resultMeta"),
    loadingState: document.getElementById("loadingState"),
    errorState: document.getElementById("errorState"),
    emptyState: document.getElementById("emptyState"),
    reviewsTable: document.getElementById("reviewsTable"),
    prevPage: document.getElementById("prevPage"),
    nextPage: document.getElementById("nextPage"),
    pageLabel: document.getElementById("pageLabel"),
    reviewDialog: document.getElementById("reviewDialog"),
    dialogTitle: document.getElementById("dialogTitle"),
    dialogBody: document.getElementById("dialogBody"),
    closeDialog: document.getElementById("closeDialog"),
  };

  function endpoint(path, params) {
    const url = new URL(coreApiBaseUrl + dashboardPrefix + path);
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) {
        url.searchParams.set(key, value);
      }
    });
    return url.toString();
  }

  async function fetchJson(url) {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const message = response.status === 503
        ? "Dashboard data is unavailable. Check Core API and database configuration."
        : `Request failed with status ${response.status}.`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  function setLoading(isLoading) {
    els.loadingState.hidden = !isLoading;
    els.refreshButton.disabled = isLoading;
    els.prevPage.disabled = isLoading || state.page <= 1;
    const hasNext = state.page * pageSize < state.total;
    els.nextPage.disabled = isLoading || !hasNext;
  }

  function setError(error) {
    const hasError = Boolean(error);
    els.errorState.hidden = !hasError;
    els.errorState.textContent = hasError ? error.message : "";
    els.connectionStatus.textContent = hasError ? "Error" : "Connected";
    els.connectionStatus.classList.toggle("error", hasError);
    els.connectionStatus.classList.toggle("ok", !hasError);
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("en-US").format(Number(value || 0));
  }

  function formatDate(value) {
    if (!value) {
      return "Not available";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString();
  }

  function text(value, fallback) {
    const normalized = value === null || value === undefined ? "" : String(value).trim();
    return normalized || fallback || "Not available";
  }

  function applySummary(summary) {
    els.metricTotalItems.textContent = formatNumber(summary.total_items);
    els.metricReviews.textContent = formatNumber(summary.total_reviews);
    els.metricAnalyzed.textContent = formatNumber(summary.analyzed_items);
    els.metricRisk.textContent = text(summary.risk_level, "None");
  }

  function applyBusinesses(businesses) {
    state.businesses = Array.isArray(businesses) ? businesses : [];
    const current = state.businessId;
    els.businessFilter.replaceChildren(new Option("All businesses", ""));
    state.businesses.forEach((business) => {
      const label = [business.name, business.branch_name].filter(Boolean).join(" - ");
      els.businessFilter.appendChild(new Option(label || `Business ${business.id}`, String(business.id)));
    });
    els.businessFilter.value = current;
  }

  function reviewRow(review) {
    const row = document.createElement("tr");
    row.tabIndex = 0;
    row.dataset.reviewId = String(review.id);

    const title = text(review.title || review.summary, "Untitled review");
    const snippet = text(review.content || review.summary, "No review content available.");
    row.innerHTML = `
      <td>${escapeHtml(text(review.business_name, "Unknown business"))}</td>
      <td><span class="chip">${escapeHtml(text(review.platform, "unknown"))}</span></td>
      <td>
        <span class="review-title">${escapeHtml(title)}</span>
        <span class="review-snippet">${escapeHtml(snippet.slice(0, 180))}</span>
      </td>
      <td><span class="chip">${escapeHtml(text(review.sentiment, "unclassified"))}</span></td>
      <td><span class="chip">${escapeHtml(text(review.risk_level, "none"))}</span></td>
      <td>${escapeHtml(formatDate(review.updated_at || review.published_at))}</td>
    `;
    row.addEventListener("click", () => openReview(review.id));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        openReview(review.id);
      }
    });
    return row;
  }

  function applyReviews(payload) {
    const items = Array.isArray(payload.items) ? payload.items : [];
    state.total = Number(payload.total || 0);
    els.reviewsTable.replaceChildren(...items.map(reviewRow));
    els.emptyState.hidden = items.length > 0;
    els.resultMeta.textContent = `${formatNumber(state.total)} reviews found`;
    els.pageLabel.textContent = `Page ${state.page}`;
  }

  async function loadDashboard() {
    setError(null);
    setLoading(true);
    try {
      const params = {
        business_id: state.businessId,
        platform: state.platform,
      };
      const [businesses, summary, reviews] = await Promise.all([
        fetchJson(endpoint("/businesses")),
        fetchJson(endpoint("/summary", { business_id: state.businessId })),
        fetchJson(endpoint("/reviews", {
          ...params,
          page: state.page,
          page_size: pageSize,
        })),
      ]);
      applyBusinesses(businesses);
      applySummary(summary);
      applyReviews(reviews);
      setError(null);
    } catch (error) {
      setError(error);
    } finally {
      setLoading(false);
    }
  }

  async function openReview(reviewId) {
    setError(null);
    try {
      const review = await fetchJson(endpoint(`/reviews/${encodeURIComponent(reviewId)}`));
      els.dialogTitle.textContent = text(review.title || review.summary, "Review detail");
      els.dialogBody.innerHTML = `
        <div class="detail-grid">
          <div><span>Business</span>${escapeHtml(text(review.business_name, "Unknown business"))}</div>
          <div><span>Platform</span>${escapeHtml(text(review.platform, "unknown"))}</div>
          <div><span>Sentiment</span>${escapeHtml(text(review.sentiment, "unclassified"))}</div>
          <div><span>Risk</span>${escapeHtml(text(review.risk_level, "none"))}</div>
        </div>
        <p>${escapeHtml(text(review.content, "No review content available."))}</p>
        ${review.recommendation ? `<p><strong>Recommendation:</strong> ${escapeHtml(review.recommendation)}</p>` : ""}
        ${review.link ? `<p><a href="${escapeAttribute(review.link)}" target="_blank" rel="noreferrer">Open source review</a></p>` : ""}
      `;
      els.reviewDialog.showModal();
    } catch (error) {
      if (error.status === 404) {
        error.message = "The selected review no longer exists.";
      }
      setError(error);
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#039;",
    })[char]);
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
  }

  function wireEvents() {
    els.apiBaseUrl.textContent = coreApiBaseUrl;
    els.businessFilter.addEventListener("change", () => {
      state.businessId = els.businessFilter.value;
      state.page = 1;
      loadDashboard();
    });
    els.platformFilter.addEventListener("change", () => {
      state.platform = els.platformFilter.value;
      state.page = 1;
      loadDashboard();
    });
    els.refreshButton.addEventListener("click", loadDashboard);
    els.resetButton.addEventListener("click", () => {
      state.businessId = "";
      state.platform = "";
      state.page = 1;
      els.businessFilter.value = "";
      els.platformFilter.value = "";
      loadDashboard();
    });
    els.prevPage.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        loadDashboard();
      }
    });
    els.nextPage.addEventListener("click", () => {
      if (state.page * pageSize < state.total) {
        state.page += 1;
        loadDashboard();
      }
    });
    els.closeDialog.addEventListener("click", () => els.reviewDialog.close());
  }

  if (window.__BI_RMP_DASHBOARD_TEST_MODE__) {
    window.__BI_RMP_DASHBOARD_TEST__ = {
      endpoint,
      loadDashboard,
      openReview,
      state,
    };
  }

  wireEvents();
  loadDashboard();
})();
