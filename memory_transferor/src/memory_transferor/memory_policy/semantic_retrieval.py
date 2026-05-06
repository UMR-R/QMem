"""Lightweight local semantic retrieval for episode candidate selection.

This module is intentionally small and dependency-free. It is not a vector
database and not an authority for memory writes. It only ranks candidate
episodes before an LLM or memory policy makes the final decision.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


SEMANTIC_STOPWORDS = {
    "user", "assistant", "episode", "summary", "topic", "context", "memory", "node",
    "用户", "助手", "助理", "建议", "推荐", "询问", "了解", "选择", "偏好", "日常", "记忆",
    "上下文", "相关", "提供", "讨论", "表达", "希望", "需要", "可以", "适合", "关于",
    "进行", "寻找", "比较", "参考", "问题", "内容", "信息", "方向", "个人", "具体",
    "进一步", "尚未", "确认", "正在", "后续", "搭配", "选项", "场景", "上下游",
}

DAILY_NOTE_SEMANTIC_ANCHORS = [
    "reusable personal daily context, life preference, personal choice, recurring criterion, small fact useful later",
    "用户的日常生活上下文、个人选择、长期偏好、反复出现的标准、以后可能有用的小事实",
    "personal communication situation, relationship boundary, wording request, response format for a real-life interaction",
    "真实生活或职场沟通场景、关系边界、回复方式、表达要求",
    "learning habit, practice preference, personal study plan, low-pressure routine, entertainment choice",
    "学习方式、练习偏好、个人计划、低压力作息、休闲娱乐选择",
]

PROJECT_SEMANTIC_ANCHORS = [
    "active project architecture, implementation plan, evaluation benchmark, dataset, roadmap, product design",
    "项目架构、工程实现、评测 benchmark、数据集、路线图、产品方案、系统设计",
    "research proposal, experiment design, paper framework, model pipeline, technical decision",
    "研究项目、实验设计、论文框架、模型 pipeline、技术决策",
]

WORKFLOW_SEMANTIC_ANCHORS = [
    "repeatable workflow, SOP, standard process, reusable template, checklist, playbook, step-by-step routine",
    "可复用工作流、SOP、标准流程、模板、清单、固定步骤、反复使用的方法",
    "trigger condition, typical steps, preferred output format, review rule, escalation rule",
    "触发条件、典型步骤、固定产出格式、review 规则、协作流程",
]


def canonical_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"([a-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
    text = re.sub(r"([\u4e00-\u9fff])([a-z0-9])", r"\1 \2", text)
    text = re.sub(r"[\-_/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def semantic_vector(value: Any) -> dict[str, float]:
    text = canonical_text(value)
    if not text:
        return {}
    weights: dict[str, float] = {}

    def add(term: str, weight: float) -> None:
        term = term.strip()
        if not term or term in SEMANTIC_STOPWORDS:
            return
        weights[term] = weights.get(term, 0.0) + weight

    for token in re.findall(r"[a-z0-9][a-z0-9_]{1,}", text):
        add(f"w:{token}", 1.0)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) <= 8:
            add(f"zh:{chunk}", 1.0)
        for size, weight in ((2, 0.6), (3, 0.9), (4, 1.1)):
            if len(chunk) < size:
                continue
            for index in range(0, len(chunk) - size + 1):
                add(f"g{size}:{chunk[index:index + size]}", weight)
    return weights


def semantic_similarity(left: Any, right: Any) -> float:
    left_vec = semantic_vector(left)
    right_vec = semantic_vector(right)
    if not left_vec or not right_vec:
        return 0.0
    shared = set(left_vec) & set(right_vec)
    if not shared:
        return 0.0
    numerator = sum(left_vec[key] * right_vec[key] for key in shared)
    left_norm = sum(value * value for value in left_vec.values()) ** 0.5
    right_norm = sum(value * value for value in right_vec.values()) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def best_semantic_similarity(text: Any, anchors: Iterable[str]) -> float:
    return max((semantic_similarity(text, anchor) for anchor in anchors), default=0.0)


def episode_support_text(episode: Any) -> str:
    display = getattr(episode, "display", {}) or {}
    display_texts: list[str] = []
    if isinstance(display, dict):
        for value in display.values():
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            if isinstance(value, dict):
                display_texts.extend(str(item or "") for item in value.values())
    return " ".join(
        str(value or "")
        for value in [
            getattr(episode, "topic", ""),
            getattr(episode, "summary", ""),
            " ".join(getattr(episode, "topics_covered", []) or []),
            " ".join(getattr(episode, "key_decisions", []) or []),
            " ".join(getattr(episode, "open_issues", []) or []),
            json.dumps(getattr(episode, "relates_to_projects", []) or [], ensure_ascii=False),
            json.dumps(getattr(episode, "relates_to_workflows", []) or [], ensure_ascii=False),
            " ".join(display_texts),
        ]
    )


def episode_semantic_score(episode: Any, anchors: Iterable[str]) -> float:
    return best_semantic_similarity(episode_support_text(episode), anchors)


def retrieve_semantic_episodes(
    episodes: Iterable[Any],
    anchors: Iterable[str],
    *,
    min_score: float = 0.08,
    max_items: int = 24,
) -> list[Any]:
    scored: list[tuple[float, int, Any]] = []
    for index, episode in enumerate(episodes):
        score = episode_semantic_score(episode, anchors)
        if score >= min_score:
            scored.append((score, index, episode))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [episode for _, _, episode in scored[:max_items]]
