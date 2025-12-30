import aiohttp
import json
import os
import re
import asyncio
from dotenv import load_dotenv

SYSTEM_MESSAGE = """
You are a strict JSON scoring agent.
Always return valid JSON matching schema provided.
"""
MAX_RETRIES = 3

class OllamaClient:
    def __init__(self, session: aiohttp.ClientSession, model=None, system_message: str = None):
        load_dotenv()
        self.base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "mistral:latest")
        self.session = session
        self.system_message = {"role": "system", "content": system_message or SYSTEM_MESSAGE}

    def _extract_json_object(self, text: str) -> dict | None:
        """
        Best-effort extraction of a single top-level JSON object from text.
        Handles cases like:
          - leading/trailing commentary
          - ```json ... ```
          - multiple lines / whitespace
        """
        if not text or not isinstance(text, str):
            return None

        cleaned = text.strip()

        # Strip common fenced code blocks
        cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        # Fast path
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

        # Find first {...} object (non-greedy), then try parse
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None

        candidate = match.group(0).strip()
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    async def call(self, prompt: str, sch, temp=0.7, top_p=0.7, top_k=10, mt: int = 1024):
        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}

        payload = {
            "model": self.model,
            "messages": [
                self.system_message,
                {"role": "user", "content": prompt},
            ],
            "format": sch,  # may be "json" or a JSON schema dict (Ollama supports both)
            "options": {
                "keep_alive": -1,
                "temperature": temp,
                "top_p": top_p,
                "top_k": top_k,
                "max_tokens": mt,
            },
        }

        timeout = aiohttp.ClientTimeout(total=3600)

        async with self.session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
            if resp.status != 200:
                raise Exception(f"Bad response {resp.status}: {await resp.text()}")

            full_response = ""
            async for line in resp.content:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                # IMPORTANT: some servers may include final content on the done chunk
                if "message" in data and isinstance(data["message"], dict) and "content" in data["message"]:
                    full_response += data["message"]["content"] or ""

                if data.get("done", False):
                    break

        # Parse JSON strictly; if it fails, try extraction; else return raw_text
        try:
            parsed = json.loads(full_response)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        extracted = self._extract_json_object(full_response)
        if extracted is not None:
            return extracted

        return {"raw_text": full_response}

    async def unload(self):
        """Unload the model from memory without deleting from disk."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "unload"}],
            "options": {
                "keep_alive": 0,
                "num_ctx": 4096
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                await resp.text()
        return ()

async def main():
    with open ('test.json','r') as file:
        data = json.load(file)

    print(data)
    user_prompt = data["user_prompt"]
    json_schema = data["json_schema"]
    temp = data["temp"]
    top_p = data["top_p"]
    top_k = data["top_k"]
    mt = data["mt"]

    SYSTEM_MESSAGE = """
                You are an expert career coach reviewing the user's resume against the description of a job to determine
                if the user would be a good fit for the job. 

                <INPUT>

                Job Description: <string>,
                    Resume: <string>,
                    Criterion: <string>,
                    Score Range: <string> 

                <OUTPUT>

                {
                    "type": "object",
                    "properties": {
                        "criterion": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "score": {"type": "number"}
                    }
                    "required": ["criterion", "reasoning", "score"]
                }

                For each request:
                - You will receive ONE Job description, a resume, a Criterion description, and a score range.        
                - Compare the Job description and the resume
                - Demonstrate careful analysis and consideration of multiple angles.
                - Use the given Criterion description for details on how to score the match.
                - Score must be within the given *Score Range*.
                - OUTPUT MUST BE VALID JSON, MATCHING THE <OUTPUT> SCHEMA EXACTLY.
                """
    session = aiohttp.ClientSession()
    client = OllamaClient(session, model="hf.co/bartowski/nvidia_Orchestrator-8B-GGUF:Q4_K_M",
                          system_message=SYSTEM_MESSAGE)
    result = await client.call(user_prompt, json_schema, temp, top_p, top_k, mt)
    await client.unload()
    await client.session.close()
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
