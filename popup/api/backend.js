(() => {
  function normalizeBaseUrl(raw) {
    return (raw || "http://127.0.0.1:8765").replace(/\/$/, "");
  }

  async function request(baseUrl, path, options = {}) {
    const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
      },
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const errorPayload = await response.json();
        if (errorPayload?.detail) message = errorPayload.detail;
        else if (errorPayload?.message) message = errorPayload.message;
      } catch {
        // Keep the generic HTTP message if the body is not JSON.
      }
      throw new Error(message);
    }

    return response.json();
  }

  window.BackendAPI = {
    getHealth(baseUrl) {
      return request(baseUrl, "/api/health");
    },

    getSettings(baseUrl) {
      return request(baseUrl, "/api/settings");
    },

    saveSettings(baseUrl, payload) {
      return request(baseUrl, "/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    testConnection(baseUrl, payload) {
      return request(baseUrl, "/api/settings/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    getSummary(baseUrl) {
      return request(baseUrl, "/api/summary");
    },

    getSyncStatus(baseUrl) {
      return request(baseUrl, "/api/sync/status");
    },

    toggleSync(baseUrl, payload) {
      return request(baseUrl, "/api/sync/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    appendConversation(baseUrl, payload) {
      return request(baseUrl, "/api/conversations/append", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    importCurrentConversation(baseUrl, payload) {
      return request(baseUrl, "/api/conversations/current/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    organizeMemory(baseUrl) {
      return request(baseUrl, "/api/memory/organize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
    },

    getMemoryCategories(baseUrl) {
      return request(baseUrl, "/api/memory/categories");
    },

    getMemoryItems(baseUrl, category) {
      return request(baseUrl, `/api/memory/items?category=${encodeURIComponent(category)}`);
    },

    exportPackage(baseUrl, payload) {
      return request(baseUrl, "/api/export/package", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    injectPackage(baseUrl, payload) {
      return request(baseUrl, "/api/inject/package", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    getMySkills(baseUrl) {
      return request(baseUrl, "/api/skills/my");
    },

    getRecommendedSkills(baseUrl) {
      return request(baseUrl, "/api/skills/recommended");
    },

    saveSkills(baseUrl, payload) {
      return request(baseUrl, "/api/skills/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    deleteSkills(baseUrl, payload) {
      return request(baseUrl, "/api/skills/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    injectSkills(baseUrl, payload) {
      return request(baseUrl, "/api/skills/inject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    importHistory(baseUrl, { platform, file }) {
      const form = new FormData();
      form.append("platform", platform);
      form.append("file", file);
      return request(baseUrl, "/api/import/history", {
        method: "POST",
        body: form,
      });
    },

    clearCache(baseUrl, payload) {
      return request(baseUrl, "/api/cache/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    getJob(baseUrl, jobId) {
      return request(baseUrl, `/api/jobs/${encodeURIComponent(jobId)}`);
    },
  };
})();
