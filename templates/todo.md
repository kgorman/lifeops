---
title: <one-line title>
owner: user-a          # one of $TODOS_OWNERS, or `shared`
status: inbox          # inbox | active | blocked | delegated | in_progress | needs_review | done | wont_do | someday

# Covey 4-quadrant classification — this is the primary lens.
#   q1: urgent + important     → do now (default assignee: me)
#   q2: not urgent + important → schedule, protect this time (default: me)
#   q3: urgent + not important → delegate (default assignee: claude)
#   q4: not urgent + not important → captured directly to someday/
quadrant:              # q1 | q2 | q3 | q4

# Covey roles — which part of life this item serves. Free-form per household.
# Examples: parent, spouse, athlete, professional, business-owner, citizen.
roles: []

assignee: me           # me | claude | waiting | <any other configured owner>
priority: none         # high | medium | low | none

# Free-form context tags (location/object/project). Different from roles.
# Examples: vehicles, garage, project-name, home, away.
tags: []

needs: []
context: ""
created: 2026-05-23
updated: 2026-05-23
github_issue:
blocked_reason:
---

<free-form notes, links, references>

## Instructions
<populated when delegating — what the assignee should do>

## Agent findings
<populated by the agent when it has output>

## Decision needed
<populated by the agent with 2-3 concrete options>
