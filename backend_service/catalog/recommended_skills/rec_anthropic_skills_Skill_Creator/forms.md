# Forms

## Trigger
需要处理与Skill Creator相关的任务时

## Output Format
结构化结果

## Standard Steps
1. For each test case, spawn two subagents in the same turn — one with the skill, one without. This is important: don't spawn the with-skill runs first and then come back for baselines later. Launch everything at once so it all finishes around the same time.
2. With-skill run:**
3. Execute this task:
4. Skill path: <path-to-skill>
