# TieItUp's Python pack: the rules read when editing Python

> **2026-10-15** · Peter · `current`
>
> Read this file when a change edits Python. It adds the study's Python-only
> rules to the 18 core rules. Devarness supports Python 3.9 and later, so
> shared code must remain compatible with that minimum.

## 6 rules apply to Python beyond the core

| ID | Rule | Source |
| --- | --- | --- |
| A-15 | Don't return None to mean 'nothing found' from a function that returns a collection; return an empty list, dict or set, or raise. | Clean Code p.119-120, book text |
| D-15 | Order a Python try's except clauses from the narrowest class to the broadest; Python takes the first match, so a parent class listed first hides its subclasses. | Python Cookbook p.606, bibliographic reference above |
| D-19 | In a Python program other people run, catch the errors their input can cause and print a plain message instead of letting a raw traceback reach them. | Python Crash Course p.193, bibliographic reference above |
| D-25 | Guard multi-step updates to state that Python threads share with a lock, and never rely on the order in which threads run or finish. | Python Source Code Analysis p.424, bibliographic reference above |
| D-26 | Create per-instance lists, dicts and sets in __init__, never as Python class attributes, which every instance of the class shares. | Core Python Programming p.485, bibliographic reference above |
| D-M6 | Give Python parameters only immutable defaults such as None, numbers or strings; for a list or dict, default to None and test it with is None. | Python Cookbook p.246-247, book text |
