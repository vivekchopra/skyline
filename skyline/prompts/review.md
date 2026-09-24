# Skyline review

You are reviewing one pull request. The structural model is below. Do not re-derive it from the line diff. Use only this data.

## Task 1. Risk register

Rank added and modified units by CRAP score times the number of dependents on that breaking change. A unit with no dependent count contributes its CRAP score alone. List the highest first. For each row: the name, the CRAP score, the dependent count, and one sentence on why a reviewer should open it. Skip low CRAP with no dependents.

## Task 2. Architecture flags

From coupling, the data model, and untested new types, list only the flags that change where code or tables belong:

- a new import, especially one the policy violations also name
- a table or column added beside a writer in a different area
- a new type whose name does not appear in a changed test file

If a section is empty, say so in one line. Do not invent findings that are not in the data.

## Structural model

{{SKYLINE_DATA}}
