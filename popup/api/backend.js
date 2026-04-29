(() => {
  function normalizeBaseUrl(raw) {
    const value = String(raw || "").trim();
    const normalized = value
      ? (value.includes("://") ? value : `http://${value}`)
      : "http://127.0.0.1:8765";
    return normalized.replace(/\/$/, "");
  }

  function extractErrorMessage(payload, fallback) {
    if (typeof payload === "string" && payload.trim()) {
      return payload.trim();
    }
    if (Array.isArray(payload)) {
      const parts = payload
        .map(item => extractErrorMessage(item, ""))
        .filter(Boolean);
      return parts.length ? parts.join("；") : fallback;
    }
    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        return payload.detail.trim();
      }
      if (payload.detail !== undefined) {
        return extractErrorMessage(payload.detail, fallback);
      }
      if (typeof payload.message === "string" && payload.message.trim()) {
        return payload.message.trim();
      }
      if (Array.isArray(payload.loc) && typeof payload.msg === "string") {
        const location = payload.loc
          .map(part => String(part))
          .filter(Boolean)
          .join(".");
        return location ? `${location}: ${payload.msg}` : payload.msg;
      }
      try {
        return JSON.stringify(payload);
      } catch {
        return fallback;
      }
    }
    return fallback;
  }

  async function request(baseUrl, path, options = {}) {
    let response;
    try {
      response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
        ...options,
        headers: {
          ...(options.headers || {}),
        },
      });
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error("无法连接到本地后端");
      }
      throw error;
    }

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const errorPayload = await response.json();
        message = extractErrorMessage(errorPayload, message);
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

    importPlatformMemory(baseUrl, payload) {
      return request(baseUrl, "/api/platform-memory/import", {
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

    getMemoryCategories(baseUrl, locale) {
      const query = new URLSearchParams();
      if (locale) query.set("locale", locale);
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request(baseUrl, `/api/memory/categories${suffix}`);
    },

    getMemoryItems(baseUrl, category, locale) {
      const query = new URLSearchParams({ category });
      if (locale) query.set("locale", locale);
      return request(baseUrl, `/api/memory/items?${query.toString()}`);
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

    refreshRecommendedSkills(baseUrl, payload = { force: true }) {
      return request(baseUrl, "/api/skills/recommended/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    saveSkills(baseUrl, payload) {
      return request(baseUrl, "/api/skills/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    exportSkills(baseUrl, payload) {
      return request(baseUrl, "/api/skills/export", {
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
