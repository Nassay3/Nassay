import OpenAI from "openai";

const apiKey = process.env["OPENROUTER_API_KEY"];

if (!apiKey) {
  console.warn("OPENROUTER_API_KEY is not configured; AI chat is disabled.");
}

export const openrouter = apiKey
  ? new OpenAI({ apiKey, baseURL: "https://openrouter.ai/api/v1" })
  : null;
