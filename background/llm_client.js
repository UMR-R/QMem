// LLM Client — 统一封装 LLM API 调用
// 目前使用 DeepSeek（与现有系统复用同一个 API Key）

const DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions";
const DEEPSEEK_MODEL = "deepseek-chat";

/**
 * 调用 LLM，返回解析后的 JSON 对象。
 * 支持三种容错解析：直接解析 → markdown 代码块 → 正则提取。
 *
 * @param {string} systemPrompt
 * @param {string} userPrompt
 * @param {string} apiKey
 * @returns {Promise<object>}  解析后的 JSON；若解析失败返回 {}
 */
export async function extractJson(systemPrompt, userPrompt, apiKey) {
  const text = await _call(systemPrompt, userPrompt, apiKey, 0.0, 2048);
  return _parseJson(text);
}

/**
 * 调用 LLM，返回纯文本。
 *
 * @param {string} systemPrompt
 * @param {string} userPrompt
 * @param {string} apiKey
 * @returns {Promise<string>}
 */
export async function summarize(systemPrompt, userPrompt, apiKey) {
  return _call(systemPrompt, userPrompt, apiKey, 0.3, 1024);
}

// ── 内部实现 ──────────────────────────────────────────────────────────────────

async function _call(systemPrompt, userPrompt, apiKey, temperature, maxTokens) {
  const resp = await fetch(DEEPSEEK_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: DEEPSEEK_MODEL,
      temperature,
      max_tokens: maxTokens,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user",   content: userPrompt   },
      ],
    }),
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => resp.statusText);
    throw new Error(`LLM API error ${resp.status}: ${err}`);
  }

  const data = await resp.json();
  return data.choices?.[0]?.message?.content ?? "";
}

function _parseJson(text) {
  // 1. 直接解析
  try { return JSON.parse(text); } catch { /* fall through */ }

  // 2. 提取 markdown 代码块中的 JSON
  const blockMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (blockMatch) {
    try { return JSON.parse(blockMatch[1].trim()); } catch { /* fall through */ }
  }

  // 3. 正则提取第一个 { ... } 或 [ ... ] 块
  const objMatch = text.match(/(\{[\s\S]*\}|\[[\s\S]*\])/);
  if (objMatch) {
    try { return JSON.parse(objMatch[1]); } catch { /* fall through */ }
  }

  console.warn("[llm_client] JSON parse failed, raw text:", text.slice(0, 200));
  return {};
}
