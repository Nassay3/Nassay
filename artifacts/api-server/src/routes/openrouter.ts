import { Router } from "express";
import { openrouter } from "../lib/openrouter";

const router = Router();

router.get("/openrouter/models", async (_req, res) => {
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
  const message = req.body?.message || "Say hello and confirm you are working.";
  try {
    const completion = await openrouter.chat.completions.create({
      model: "openai/gpt-4o-mini",
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
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

export default router;
