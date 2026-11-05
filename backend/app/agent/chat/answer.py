"""Le second appel du chat : écrire la réponse à partir des passages trouvés, en streaming (chaque morceau part vers le
navigateur dès qu'il est écrit)."""

from app.agent import llm, model_output, model_router, usage
from app.agent.chat.events import ChatEvents


async def stream_answer(*, model: str | None, system: str, messages: list[dict], events: ChatEvents) -> str:
    stream = await llm.client().chat.completions.create(
        model=model or await model_router.default_model(),
        messages=[{"role": "system", "content": system}, *messages],
        stream=True,
        stream_options={"include_usage": True},
        temperature=0.2,
        max_tokens=2000,
    )
    written = ""  # tout ce que le modèle a écrit
    shown = ""  # ce que le navigateur en a reçu : jamais du JSON, seulement le texte de la réponse
    used = None
    served_by = model
    async for chunk in stream:
        served_by = getattr(chunk, "model", None) or served_by
        if chunk.usage:
            used = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            written += chunk.choices[0].delta.content
            visible = model_output.visible_answer(written)
            if visible != shown and visible.startswith(shown):
                await events.delta(visible[len(shown) :])
                shown = visible
    await events.flush()
    await usage.record(served_by, used)
    # Ce qui a été montré et ce qui est déposé sont le même texte ; vide (JSON sans réponse, rien écrit) quand il n'y a
    # rien à montrer : l'appelant se replie alors sur les outils.
    answer = model_output.final_answer(written)
    if answer.startswith(shown) and len(answer) > len(shown):
        await events.delta(answer[len(shown) :])
        await events.flush()
    return answer
