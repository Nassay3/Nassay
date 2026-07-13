import OpenAI from "openai";

const apiKey = process.env["OPENROUTER_API_KEY"];

if (!apiKey) {
  console.error("OPENROUTER_API_KEY is not configured.");
  process.exit(1);
}

export const openrouter = new OpenAI({
  apiKey,
  baseURL: "https://openrouter.ai/api/v1",
});
