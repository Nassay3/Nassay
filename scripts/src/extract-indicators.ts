import fs from "node:fs";
import { openrouter } from "../../artifacts/api-server/src/lib/openrouter";

const imagePath = process.argv[2] ?? "screenshots/notion-indicators.png";
const base64 = fs.readFileSync(imagePath, "base64");

const response = await openrouter.chat.completions.create({
  model: "openai/gpt-4o-mini",
  messages: [
    {
      role: "system",
      content: "You extract TradingView indicator names from screenshots. List every indicator name exactly as shown. Return only a clean list, one per line.",
    },
    {
      role: "user",
      content: [
        { type: "text", text: "Extract all TradingView indicators and scripts from this page." },
        { type: "image_url", image_url: { url: `data:image/png;base64,${base64}` } },
      ],
    },
  ],
});

console.log(response.choices[0]?.message?.content ?? "No response");
