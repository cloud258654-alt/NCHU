const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appScript = fs.readFileSync(path.join(__dirname, "..", "frontend", "app.js"), "utf8");

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function createElement(id) {
  const events = {};
  return {
    id,
    tagName: id,
    children: [],
    dataset: {},
    hidden: false,
    disabled: false,
    opened: false,
    value: "",
    textContent: "",
    innerHTML: "",
    tabIndex: -1,
    classList: {
      values: new Set(),
      toggle(name, force) {
        if (force) {
          this.values.add(name);
        } else {
          this.values.delete(name);
        }
      },
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    replaceChildren(...children) {
      this.children = children;
    },
    addEventListener(name, callback) {
      events[name] = callback;
    },
    dispatch(name, event) {
      if (events[name]) {
        return events[name](event || {});
      }
      return undefined;
    },
    showModal() {
      this.opened = true;
    },
    close() {
      this.opened = false;
    },
  };
}

function createDocument() {
  const ids = [
    "connectionStatus",
    "apiBaseUrl",
    "businessFilter",
    "platformFilter",
    "refreshButton",
    "resetButton",
    "metricTotalItems",
    "metricReviews",
    "metricAnalyzed",
    "metricRisk",
    "resultMeta",
    "loadingState",
    "errorState",
    "emptyState",
    "reviewsTable",
    "prevPage",
    "nextPage",
    "pageLabel",
    "reviewDialog",
    "dialogTitle",
    "dialogBody",
    "closeDialog",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, createElement(id)]));
  return {
    elements,
    getElementById(id) {
      if (!elements[id]) {
        elements[id] = createElement(id);
      }
      return elements[id];
    },
    createElement(tagName) {
      return createElement(tagName);
    },
  };
}

function makeOption(label, value) {
  return {
    label,
    text: label,
    textContent: label,
    value: String(value),
  };
}

function defaultRoute(parsed) {
  if (parsed.pathname.endsWith("/businesses")) {
    return response(200, [
      {
        id: 7,
        name: "Demo Shop",
        branch_name: "Main",
      },
    ]);
  }
  if (parsed.pathname.endsWith("/summary")) {
    return response(200, {
      total_items: 9,
      total_reviews: 5,
      analyzed_items: 4,
      risk_level: "medium",
    });
  }
  if (parsed.pathname.endsWith("/reviews/101")) {
    return response(200, {
      id: 101,
      business_name: "Demo Shop",
      platform: "google_maps",
      title: "Useful review",
      content: "The review detail body.",
      sentiment: "positive",
      risk_level: "high",
      critical: true,
      critical_signals: ["medical escalation"],
      escalation_level: "critical",
      human_review_required: true,
    });
  }
  if (parsed.pathname.endsWith("/reviews")) {
    return response(200, {
      items: [
        {
          id: 101,
          business_name: "Demo Shop",
          platform: "google_maps",
          title: "Useful review",
          content: "Compact review text.",
          sentiment: "positive",
          risk_level: "high",
          critical: true,
          critical_signals: ["medical escalation"],
          escalation_level: "critical",
          human_review_required: true,
          updated_at: "2026-07-18T00:00:00Z",
        },
      ],
      page: Number(parsed.searchParams.get("page") || "1"),
      page_size: 20,
      total: 41,
    });
  }
  return response(404, {});
}

async function runDashboard(route = defaultRoute) {
  const document = createDocument();
  const calls = [];
  const sandbox = {
    console,
    document,
    Intl,
    Option: makeOption,
    URL,
    window: {
      __BI_RMP_DASHBOARD_CONFIG__: {
        coreApiBaseUrl: "http://core.example.test",
        dashboardApiPrefix: "/api/dashboard",
      },
      __BI_RMP_DASHBOARD_TEST_MODE__: true,
    },
    fetch: async (url) => {
      calls.push(String(url));
      const parsed = new URL(String(url));
      return route(parsed);
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(appScript, sandbox, { filename: "app.js" });
  await flush();
  await flush();
  return {
    api: sandbox.window.__BI_RMP_DASHBOARD_TEST__,
    calls,
    elements: document.elements,
  };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

function assertNoDirectSupabase(calls) {
  const forbidden = [
    "supabase" + ".co/rest/v1",
    "/api/" + "supabase-query",
    "SUPABASE" + "_SERVICE_ROLE_KEY",
    "DATABASE" + "_URL",
  ];
  assert(calls.every((call) => forbidden.every((token) => !call.includes(token))), calls.join("\n"));
}

async function testCorrectCoreApiCalls() {
  const { calls } = await runDashboard();
  assert(calls.some((call) => call === "http://core.example.test/api/dashboard/businesses"));
  assert(calls.some((call) => call === "http://core.example.test/api/dashboard/summary"));
  assert(calls.some((call) => call.includes("/api/dashboard/reviews?page=1&page_size=20")));
  assertNoDirectSupabase(calls);
}

async function testBusinessesNormalAndEmpty() {
  const normal = await runDashboard();
  assert.strictEqual(normal.elements.businessFilter.children.length, 2);

  const empty = await runDashboard((parsed) => {
    if (parsed.pathname.endsWith("/businesses")) {
      return response(200, []);
    }
    return defaultRoute(parsed);
  });
  assert.strictEqual(empty.elements.businessFilter.children.length, 1);
}

async function testSummaryNormalAndError() {
  const normal = await runDashboard();
  assert.strictEqual(normal.elements.metricTotalItems.textContent, "9");
  assert.strictEqual(normal.elements.metricRisk.textContent, "medium");

  const broken = await runDashboard((parsed) => {
    if (parsed.pathname.endsWith("/summary")) {
      return response(503, {});
    }
    return defaultRoute(parsed);
  });
  assert.strictEqual(broken.elements.errorState.hidden, false);
  assert(broken.elements.errorState.textContent.includes("Dashboard data is unavailable"));
}

async function testReviewsNormalAndEmpty() {
  const normal = await runDashboard();
  assert.strictEqual(normal.elements.reviewsTable.children.length, 1);
  assert(normal.elements.reviewsTable.children[0].innerHTML.includes("Manual review"));
  assert.strictEqual(normal.elements.emptyState.hidden, true);

  const empty = await runDashboard((parsed) => {
    if (parsed.pathname.endsWith("/reviews")) {
      return response(200, { items: [], page: 1, page_size: 20, total: 0 });
    }
    return defaultRoute(parsed);
  });
  assert.strictEqual(empty.elements.reviewsTable.children.length, 0);
  assert.strictEqual(empty.elements.emptyState.hidden, false);
}

async function testPaginationAndFilters() {
  const dashboard = await runDashboard();
  dashboard.elements.nextPage.dispatch("click");
  await flush();
  assert(dashboard.calls.some((call) => call.includes("page=2")));

  dashboard.elements.businessFilter.value = "7";
  dashboard.elements.businessFilter.dispatch("change");
  await flush();
  assert(dashboard.calls.some((call) => call.includes("business_id=7")));

  dashboard.elements.platformFilter.value = "ptt";
  dashboard.elements.platformFilter.dispatch("change");
  await flush();
  assert(dashboard.calls.some((call) => call.includes("platform=ptt")));
}

async function testReviewDetail200And404() {
  const dashboard = await runDashboard();
  await dashboard.api.openReview(101);
  await flush();
  assert.strictEqual(dashboard.elements.reviewDialog.opened, true);
  assert(dashboard.calls.some((call) => call.endsWith("/api/dashboard/reviews/101")));
  assert(dashboard.elements.dialogBody.innerHTML.includes("Critical incident"));
  assert(dashboard.elements.dialogBody.innerHTML.includes("Manual review"));
  assert(dashboard.elements.dialogBody.innerHTML.includes("Critical signals"));

  const notFound = await runDashboard((parsed) => {
    if (parsed.pathname.endsWith("/reviews/404")) {
      return response(404, {});
    }
    return defaultRoute(parsed);
  });
  await notFound.api.openReview(404);
  await flush();
  assert.strictEqual(notFound.elements.errorState.hidden, false);
  assert(notFound.elements.errorState.textContent.includes("selected review no longer exists"));
}

async function testCoreApiUnavailable() {
  const dashboard = await runDashboard(() => response(503, {}));
  assert.strictEqual(dashboard.elements.errorState.hidden, false);
  assert(dashboard.elements.errorState.textContent.includes("Dashboard data is unavailable"));
}

async function main() {
  await testCorrectCoreApiCalls();
  await testBusinessesNormalAndEmpty();
  await testSummaryNormalAndError();
  await testReviewsNormalAndEmpty();
  await testPaginationAndFilters();
  await testReviewDetail200And404();
  await testCoreApiUnavailable();
  console.log("frontend behavior tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
