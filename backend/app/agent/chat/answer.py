"""Le second appel du chat : écrire la réponse à partir des passages trouvés, en streaming (chaque morceau part vers le
navigateur dès qu'il est écrit)."""

from app.agent import llm, usage
from app.agent.chat.events import ChatEvents
from app.agent.runner import settings


async def stream_answer(*, model: str | None, system: str, messages: list[dict], events: ChatEvents) -> str:
    stream = await llm.client().chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        stream=True,
        stream_options={"include_usage": True},
        temperature=0.2,
        max_tokens=2000,
    )
    parts: list[str] = []
    used = None
    served_by = model
    async for chunk in stream:
        served_by = getattr(chunk, "model", None) or served_by
        if chunk.usage:
            used = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            text = chunk.choices[0].delta.content
            parts.append(text)
            await events.delta(text)
    await events.flush()
    await usage.record(served_by, used)
    return "".join(parts)
