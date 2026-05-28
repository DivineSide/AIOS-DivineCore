"""LLM call wrappers. Uses OpenAI SDK against OpenRouter — same pattern as fathom/categorizer.py."""

import json

from openai import OpenAI

from settings import settings

from . import prompts


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def proposal_fields(job_description: str) -> dict:
    """Return {titleOfSystem, briefExplanationOfSystem, stepByStepBulletPoints, leftToRightFlowWithArrows, aboutMeBulletPoints}."""
    response = _client().chat.completions.create(
        model=settings.UPWORK_PROPOSAL_FIELDS_MODEL,
        temperature=0.6,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompts.PROPOSAL_FIELDS_SYSTEM},
            {"role": "user", "content": prompts.PROPOSAL_FIELDS_PROMPT + "\n\n---\n\nJob description:\n" + job_description},
        ],
    )
    return json.loads(response.choices[0].message.content or "{}")


def application_copy(job_description: str) -> str:
    """Return the application body string with $$$ placeholder still inside."""
    response = _client().chat.completions.create(
        model=settings.UPWORK_APPLICATION_MODEL,
        temperature=0.6,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompts.APPLICATION_COPY_SYSTEM},
            {"role": "user", "content": prompts.APPLICATION_COPY_PROMPT + "\n\n---\n\nJob description:\n" + job_description},
        ],
    )
    parsed = json.loads(response.choices[0].message.content or "{}")
    return parsed.get("proposal", "")
