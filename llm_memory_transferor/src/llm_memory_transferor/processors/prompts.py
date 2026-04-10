"""LLM prompts used by memory processors."""

_PROFILE_SYSTEM = """You are a memory extraction specialist. Given chat history and platform memory signals,
extract stable user identity information. Output ONLY valid JSON matching this schema:
{
  "name_or_alias": "",
  "role_identity": "",
  "domain_background": [],
  "organization_or_affiliation": "",
  "common_languages": [],
  "primary_task_types": [],
  "long_term_research_or_work_focus": []
}
Rules:
- Only include fields with clear evidence.
- domain_background: list of domain areas (e.g. "machine learning", "product management").
- primary_task_types: what the user repeatedly asks the model to help with.
- Leave fields empty ("" or []) if no evidence.
- Do NOT guess or hallucinate."""

_PREFERENCE_SYSTEM = """You are a memory extraction specialist. Given chat history and platform memory signals,
extract the user's stable output and interaction preferences. Output ONLY valid JSON:
{
  "style_preference": [],
  "terminology_preference": [],
  "formatting_constraints": [],
  "forbidden_expressions": [],
  "language_preference": "",
  "revision_preference": [],
  "response_granularity": ""
}
Rules:
- style_preference: e.g. ["no bullet points", "use numbered lists", "terse responses"].
- forbidden_expressions: phrases the user explicitly asked NOT to use.
- language_preference: primary language (e.g. "English", "Chinese", "English+Chinese mix").
- response_granularity: "concise" | "detailed" | "step-by-step" | "".
- Only include what has clear evidence from the conversation."""

_PROJECTS_SYSTEM = """You are a memory extraction specialist. Given a digest of episodic memories,
identify the user's active long-running projects. Output ONLY valid JSON:
[
  {
    "project_name": "",
    "project_goal": "",
    "current_stage": "",
    "key_terms": {},
    "finished_decisions": [],
    "unresolved_questions": [],
    "relevant_entities": [],
    "important_constraints": [],
    "next_actions": [],
    "is_active": true
  }
]
Rules:
- A project is any named system, model, paper, tool, or body of work the user is actively building or researching.
  Examples: a model called "FaceGPT", a paper submitted to CVPR, a codebase the user is developing.
- Infer projects from named entities, recurring topics, and paper/model names that appear across multiple episodes — even if individual episodes only asked for writing help, debugging, or evaluation.
- key_terms: {term: definition} dict of project-specific vocabulary.
- finished_decisions: things already decided and agreed upon.
- unresolved_questions: open items that need future work.
- Return [] only if there is genuinely no named ongoing work across all episodes."""

_WORKFLOWS_SYSTEM = """You are a memory extraction specialist. Given chat history and platform memory signals,
identify recurring workflow patterns the user applies frequently. Output ONLY valid JSON:
[
  {
    "workflow_name": "",
    "trigger_condition": "",
    "typical_steps": [],
    "preferred_artifact_format": "",
    "review_style": "",
    "escalation_rule": "",
    "reuse_frequency": "",
    "occurrence_count": 1
  }
]
Rules:
- Only include workflows that appear in multiple different conversations.
- typical_steps: ordered list of steps the user follows.
- reuse_frequency: "daily" | "weekly" | "per-project" | "ad-hoc".
- Return [] if no recurring workflows found."""

_EPISODE_SYSTEM = """You are a memory extraction specialist. Given one conversation,
produce a structured episode record. Output ONLY valid JSON:
{
  "topic": "",
  "topics_covered": [],
  "summary": "",
  "key_decisions": [],
  "open_issues": [],
  "relates_to_profile": false,
  "relates_to_preferences": false,
  "relates_to_projects": [],
  "relates_to_workflows": []
}
Rules:
- topic: 5-10 word title for the conversation.
- topics_covered: list of all distinct subjects discussed (e.g. ["NaN gradients", "model architecture", "training pipeline"]).
- summary: 2-4 sentences capturing the core outcome and what was accomplished.
- key_decisions: concrete decisions or conclusions reached.
- open_issues: questions or tasks left unresolved.
- relates_to_profile: true if the conversation reveals stable facts about the user (identity, role, domain, language).
- relates_to_preferences: true if the conversation reveals how the user wants responses formatted or styled.
- relates_to_projects: list of project names for any named system, paper, model, tool, or piece of work the user is building or researching.
  Examples: if the user discusses "FaceGPT", include "FaceGPT". If they discuss a CVPR paper submission, include the paper name or "CVPR paper".
  Include the project even if the immediate task is writing help, debugging, or evaluation — the project is what the work belongs to.
  Use [] only if the conversation has no connection to any named ongoing work.
- relates_to_workflows: list of workflow/process names if a recurring task pattern was followed (e.g. "paper revision", "prompt engineering"); [] otherwise.
- A conversation may relate to multiple memory types simultaneously — set all that apply.
- A conversation may relate to NO memory type (e.g. casual chat, greetings, one-off unrelated questions) — leave all flags false/[]. This is valid and expected.
- Be concise and factual. Do NOT hallucinate project names not mentioned in the conversation."""

_DELTA_SYSTEM = """You are a memory delta specialist. Given a new conversation and the current memory state,
identify ONLY what should be updated in the memory. Do NOT repeat already-known information.

Output ONLY valid JSON with this structure:
{
  "profile_updates": {},
  "preference_updates": {
    "add_style": [],
    "add_forbidden": [],
    "update_language": "",
    "update_granularity": ""
  },
  "project_updates": [
    {
      "project_name": "",
      "action": "update|create",
      "stage_update": "",
      "new_decisions": [],
      "new_questions": [],
      "resolved_questions": [],
      "new_next_actions": []
    }
  ],
  "workflow_updates": [
    {
      "workflow_name": "",
      "action": "confirm|create",
      "steps_update": []
    }
  ],
  "episode": {
    "topic": "",
    "summary": "",
    "key_decisions": [],
    "open_issues": [],
    "related_project": ""
  },
  "is_noise": false
}

Rules:
- profile_updates: only fields that changed or are newly confirmed.
- preference_updates: only newly expressed preferences.
- is_noise: true if the conversation has no memory-worthy content.
- Be conservative: when in doubt, mark as noise or accumulate."""
