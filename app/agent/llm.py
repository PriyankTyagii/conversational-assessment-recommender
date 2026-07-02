from app.config import settings


class LLMUnavailableError(RuntimeError):
    pass


def generate(system_prompt: str, user_prompt: str) -> str:
    """Single-call LLM generation, provider selected via settings.

    Kept to one call per turn so a chat request has a single point of
    external latency, which matters for the 30s per-call timeout budget.
    """
    if settings.llm_provider == "groq":
        return _generate_groq(system_prompt, user_prompt)
    if settings.llm_provider == "gemini":
        return _generate_gemini(system_prompt, user_prompt)
    if settings.llm_provider == "openrouter":
        return _generate_openrouter(system_prompt, user_prompt)
    raise LLMUnavailableError(f"Unknown LLM provider: {settings.llm_provider}")


def _generate_groq(system_prompt: str, user_prompt: str) -> str:
    if not settings.groq_api_key:
        raise LLMUnavailableError("GROQ_API_KEY is not configured")

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        timeout=settings.request_timeout_seconds,
    )
    return completion.choices[0].message.content


def _generate_openrouter(system_prompt: str, user_prompt: str) -> str:
    if not settings.openrouter_api_key:
        raise LLMUnavailableError("OPENROUTER_API_KEY is not configured")

    import requests

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={
            "model": settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _generate_gemini(system_prompt: str, user_prompt: str) -> str:
    if not settings.gemini_api_key:
        raise LLMUnavailableError("GEMINI_API_KEY is not configured")

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model, system_instruction=system_prompt)
    response = model.generate_content(user_prompt)
    return response.text
