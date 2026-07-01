# Thinking Pause — Communicating Deliberation to Users

## The Problem

When an AI pauses for more than a few seconds, humans assume it **froze** — not that it's **thinking**. This is because humans are used to tools that either respond instantly or crash. AI deliberation is a new category that doesn't have a UX signal.

The result: humans interrupt the AI mid-thought, restart the process, or lose trust — even when the AI is doing its best work.

## The Principle

> **Two seconds of thinking upfront saves three hours of audit-search-fix loops later.**

But the AI needs to *communicate* that it's thinking, not stuck. The signal must be:
- **Lightweight** — not a progress bar or constant chatter
- **Occasional** — only when the deliberation takes noticeably long (>3-5 seconds)
- **Human-readable** — plain English, not technical jargon
- **Reassuring** — convey "I'm working through options" not "I'm stuck"

## Implementation

The MCP should support a `thinking_pause` notification pattern. When the AI is doing something that takes time (architecture design, guard evaluation, complex refactoring), it should emit a brief status message:

```text
"Taking a moment to think through a few different approaches — this part is tricky, want to make sure we get it right. Should just be a moment."
```

Key characteristics:
1. **Time-boxed**: Only fires after N seconds of processing
2. **Non-blocking**: Doesn't interrupt the AI's work, just notifies
3. **Specific**: Explains *what* is being thought about (not generic "working...")
4. **Confident**: "I'm deliberating" not "I'm confused"

## Examples

| Situation | Bad signal | Good signal |
|---|---|---|
| Architecture design | *(silent for 30s)* | "Thinking through the module boundaries — want to make sure the service layer stays clean. One moment." |
| Guard evaluation | *(silent for 15s)* | "Checking 12 guards across 47 files — this takes a moment. Still working." |
| Complex refactor | *(silent for 20s)* | "Working through the safest way to split this function. A few options on the table — picking the best one." |
| Planning | *(silent for 25s)* | "Mapping out the implementation phases. Want to get the order right so we don't paint ourselves into a corner." |

## When NOT to Use

- Quick operations (<3 seconds) — silence is fine
- Errors — errors should be reported as errors, not "thinking"
- Clarification questions — those are direct prompts to the user, not status updates

## Integration Points

This should be a lightweight utility function in the MCP:

```python
async def notify_thinking(context: str, elapsed_seconds: float):
    """Emit a 'still thinking' notification when deliberation exceeds threshold."""
    if elapsed_seconds < 3.0:
        return  # Too fast to need a notification
    # Emit a single notification, not a stream
    message = f"Taking a moment to think through {context} — want to get this right. Should just be a moment."
    # Send via MCP notification or stdout, depending on transport
```

The AI calls this at natural checkpoints:
- Before starting a complex operation
- After completing a sub-step of a multi-step process
- When the elapsed time exceeds the threshold

## The Deeper Point

This isn't just a UX nicety. It's about **calibrating trust**. When humans understand *why* the AI is taking time, they're more patient and more trusting of the output. The silence-to-trust ratio matters.

The guard system already forces the AI to think before shipping. The thinking pause makes that thinking *visible* to the human — so they know the AI is working *with* them, not just generating code *at* them.
