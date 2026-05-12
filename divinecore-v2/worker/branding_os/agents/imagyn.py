import os
import json
import httpx
import psycopg2
import logging
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from openai import OpenAI
import anthropic

from settings import settings

logger = logging.getLogger(__name__)

# ── Clients ────────────────────────────────────────────────────────────────────
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
openrouter_client = OpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
)

# ── Constants ──────────────────────────────────────────────────────────────────
IMAGYN_BOT_ID = "1496791428020572230"
SESSION_KEY = "imagyn_global_memory"
MEMORY_LIMIT = 15
VALID_CHAT_ROLES = {"system", "assistant", "user", "function", "tool", "developer"}

SYSTEM_PROMPT = open(
    os.path.join(os.path.dirname(__file__), "IMAGYN_system_prompt.md")
).read()

ROUTER_SYSTEM_PROMPT = """You are a model router. Your only job is to read an incoming message and return exactly one of these two strings — nothing else:

claude-sonnet-4-6
gpt-4o-mini

Rules:
- Return claude-sonnet-4-6 for: complex idea generation, creative writing, strategy, deep analysis, anything requiring nuanced reasoning
- Return gpt-4o-mini for: simple conversation, quick clarifying questions, short replies, lightweight tasks

Return only the model name. No explanation. No punctuation. No extra text."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the Kallaway Core Knowledge Base in Supabase. "
                "Call this before asking clarifying questions and before generating any ideas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "categories": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["Hook", "Format", "Emotion"]},
                        "description": (
                            "Use ['Format', 'Emotion'] when starting a conversation. "
                            "Add 'Hook' when angle and feeling are agreed and you need the title/opening."
                        )
                    }
                },
                "required": ["categories"]
            }
        }
    }
]

ANTHROPIC_TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the Kallaway Core Knowledge Base in Supabase. "
            "Call this before asking clarifying questions and before generating any ideas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["Hook", "Format", "Emotion"]},
                    "description": (
                        "Use ['Format', 'Emotion'] when starting a conversation. "
                        "Add 'Hook' when angle and feeling are agreed."
                    )
                }
            },
            "required": ["categories"]
        }
    }
]


# ── Brain Router ───────────────────────────────────────────────────────────────
def route_model(message: str) -> str:
    router_messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": message}
    ]
    try:
        response = openrouter_client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages=router_messages,
            max_tokens=10,
            temperature=0,
        )
        model = response.choices[0].message.content.strip()
        if model in ("claude-sonnet-4-6", "gpt-4o-mini"):
            return model
    except Exception:
        pass

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=router_messages,
            max_tokens=10,
            temperature=0,
        )
        model = response.choices[0].message.content.strip()
        if model in ("claude-sonnet-4-6", "gpt-4o-mini"):
            return model
    except Exception:
        pass

    return "gpt-4o-mini"


# ── Database ───────────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(settings.SUPABASE_DB_URL)


def load_history(conn) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT role, content FROM imagyn_messages
            WHERE session_id = %s
            AND role IN ('system', 'assistant', 'user', 'function', 'tool', 'developer')
            AND content IS NOT NULL
            ORDER BY created_at DESC
            LIMIT %s
        """, (SESSION_KEY, MEMORY_LIMIT))
        rows = cur.fetchall()

    history: list[dict] = []
    skipped_rows = 0
    for row in reversed(rows):
        role = row.get("role")
        content = row.get("content")
        if role not in VALID_CHAT_ROLES:
            skipped_rows += 1
            continue
        if not isinstance(content, str) or not content.strip():
            skipped_rows += 1
            continue
        history.append({"role": role, "content": content})

    if skipped_rows:
        logger.warning("IMAGYN skipped %s invalid history rows for session %s", skipped_rows, SESSION_KEY)

    return history


def save_turn(conn, user_content: str, assistant_content: str):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO imagyn_messages (session_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
            (SESSION_KEY, "user", user_content, now)
        )
        cur.execute(
            "INSERT INTO imagyn_messages (session_id, role, content, created_at) VALUES (%s, %s, %s, %s)",
            (SESSION_KEY, "assistant", assistant_content, now)
        )
    conn.commit()


def search_knowledge_base(categories: list[str]) -> list[dict]:
    conn = get_db()
    placeholders = ",".join(["%s"] * len(categories))
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"SELECT title, category, core_lesson, full_explanation FROM branding_knowledge_base WHERE category IN ({placeholders})",
            tuple(categories)
        )
        results = [dict(r) for r in cur.fetchall()]
    conn.close()
    return results


# ── Discord ────────────────────────────────────────────────────────────────────
async def send_discord_reply(channel_id: str, content: str, reply_to_id: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {settings.IMAGYN_BOT_TOKEN}"},
            json={"content": content, "message_reference": {"message_id": reply_to_id}}
        )


# ── Agentic Loop — OpenAI ──────────────────────────────────────────────────────
def run_openai_compatible_loop(client: OpenAI, model: str, messages: list[dict]) -> str:
    while True:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        choice = response.choices[0].message

        if not choice.tool_calls:
            return choice.content

        messages.append(choice)
        for tc in choice.tool_calls:
            args = json.loads(tc.function.arguments)
            results = search_knowledge_base(args["categories"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(results)
            })


def run_gpt_loop(messages: list[dict]) -> str:
    if settings.OPENROUTER_API_KEY:
        try:
            return run_openai_compatible_loop(
                openrouter_client,
                "openai/gpt-4o-mini",
                [dict(message) for message in messages],
            )
        except Exception:
            logger.exception("IMAGYN OpenRouter GPT loop failed; falling back to OpenAI")

    return run_openai_compatible_loop(
        openai_client,
        "gpt-4o-mini",
        [dict(message) for message in messages],
    )


# ── Agentic Loop — Anthropic ───────────────────────────────────────────────────
def run_anthropic_loop(messages: list[dict]) -> str:
    anthropic_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m["role"] in ("user", "assistant")
    ]

    while True:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=anthropic_messages,
            tools=ANTHROPIC_TOOLS,
        )

        if response.stop_reason == "end_turn":
            return next(b.text for b in response.content if hasattr(b, "text"))

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                results = search_knowledge_base(block.input["categories"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(results)
                })

        anthropic_messages.append({"role": "assistant", "content": response.content})
        anthropic_messages.append({"role": "user", "content": tool_results})


# ── Main Entry Point ───────────────────────────────────────────────────────────
async def run(username: str, message: str, channel_id: str, message_id: str):
    message = message.replace(f"<@{IMAGYN_BOT_ID}>", "IMAGYN").strip()

    selected_model = route_model(message)

    conn = get_db()
    history = load_history(conn)
    messages = history + [{"role": "user", "content": f"{username}: {message}"}]

    if selected_model == "claude-sonnet-4-6":
        try:
            reply = run_anthropic_loop(messages)
        except Exception:
            logger.exception("IMAGYN Anthropic loop failed; falling back to GPT loop")
            reply = run_gpt_loop(messages)
    else:
        reply = run_gpt_loop(messages)

    save_turn(conn, f"{username}: {message}", reply)
    conn.close()
    await send_discord_reply(channel_id, reply, message_id)

    return reply
