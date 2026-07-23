import { Router } from "express";
import { openrouter } from "../lib/openrouter";

const router = Router();

const FREE_MODELS = [
  "tencent/hy3:free",
  "poolside/laguna-xs-2.1:free",
  "cohere/north-mini-code:free",
  "nvidia/nemotron-3.5-content-safety:free",
  "nvidia/nemotron-3-ultra-550b-a55b:free",
  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
  "poolside/laguna-m.1:free",
  "google/gemma-4-26b-a4b-it:free",
  "google/gemma-4-31b-it:free",
  "nvidia/nemotron-3-super-120b-a12b:free",
  "liquid/lfm-2.5-1.2b-thinking:free",
  "liquid/lfm-2.5-1.2b-instruct:free",
  "nvidia/nemotron-3-nano-30b-a3b:free",
  "nvidia/nemotron-nano-12b-v2-vl:free",
  "qwen/qwen3-next-80b-a3b-instruct:free",
  "nvidia/nemotron-nano-9b-v2:free",
  "openai/gpt-oss-120b:free",
  "openai/gpt-oss-20b:free",
  "qwen/qwen3-coder:free",
  "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
  "meta-llama/llama-3.3-70b-instruct:free",
  "meta-llama/llama-3.2-3b-instruct:free",
  "nousresearch/hermes-3-llama-3.1-405b:free",
];

router.get("/openrouter/models", async (_req, res) => {
  if (!openrouter) { res.status(503).json({ ok: false, error: "AI chat is not configured" }); return; }
  try {
    const response = await openrouter.models.list();
    const modelIds = response.data
      .slice(0, 50)
      .map((m) => m.id)
      .filter(Boolean);
    res.json({
      ok: true,
      count: response.data.length,
      models: modelIds,
    });
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

router.post("/openrouter/chat", async (req, res) => {
  if (!openrouter) { res.status(503).json({ ok: false, error: "AI chat is not configured" }); return; }
  const model = req.body?.model || "openai/gpt-4o-mini";
  const message = req.body?.message || "Say hello and confirm you are working.";
  try {
    const completion = await openrouter.chat.completions.create({
      model,
      messages: [{ role: "user", content: message }],
    });
    res.json({
      ok: true,
      model: completion.model,
      content: completion.choices[0]?.message?.content,
    });
  } catch (err) {
    res.status(500).json({
      ok: false,
      model,
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

router.get("/openrouter/benchmark", async (_req, res) => {
  if (!openrouter) { res.status(503).json({ ok: false, error: "AI chat is not configured" }); return; }
  const client = openrouter;
  const prompt = `Answer only with a single digit (no explanation): What is 18 + 23?`;
  const results = await Promise.all(
    FREE_MODELS.map(async (model) => {
      const start = Date.now();
      try {
        const completion = await client.chat.completions.create({
          model,
          messages: [{ role: "user", content: prompt }],
          temperature: 0,
        });
        const content = completion.choices[0]?.message?.content?.trim() || "";
        const isCorrect = /41/.test(content) && !/\d{3,}/.test(content);
        return {
          model,
          ok: true,
          latencyMs: Date.now() - start,
          answer: content,
          score: isCorrect ? 1 : 0,
        };
      } catch (err) {
        return {
          model,
          ok: false,
          latencyMs: Date.now() - start,
          answer: "",
          score: 0,
          error: err instanceof Error ? err.message : String(err),
        };
      }
    }),
  );
  res.json({
    ok: true,
    prompt,
    tested: results.length,
    results: results.sort((a, b) => b.score - a.score || a.latencyMs - b.latencyMs),
  });
});

router.get("/openrouter/usage", async (_req, res) => {
  if (!process.env["OPENROUTER_API_KEY"]) { res.status(503).json({ ok: false, error: "AI chat is not configured" }); return; }
  try {
    const response = await fetch("https://openrouter.ai/api/v1/auth/key", {
      headers: { Authorization: `Bearer ${process.env["OPENROUTER_API_KEY"]}` },
    });
    const data = (await response.json()) as { data?: unknown };
    res.json({
      ok: response.ok,
      data: data.data,
    });
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

export default router;
