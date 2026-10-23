# TieItUp's C pack: the rules read when editing C

> **2026-10-15** · Peter · `current`
>
> Read this file when a change edits C or a header. It adds the study's C-only
> rules to the 18 core rules. Book titles and page references retain their
> bibliographic attribution.

## 14 rules apply to C beyond the core

| ID | Rule | Source |
| --- | --- | --- |
| A-M4 | In C, write a function instead of a function-like macro; if one is unavoidable, parenthesize its body and every parameter, and never pass it an argument with side effects. | The Practice of Programming p.14-15, book text |
| A-M5 | When a function transforms its input, return the result instead of writing it into an argument; if it must change state, change its own object's state. | Clean Code p.55-56, p.59-60, book text |
| A-M6 | In C, let `sizeof` give every size: `sizeof buf` or `sizeof array[0]`, never a written 2, 4 or 1024 that must match a declaration. | The Practice of Programming p.17, book text |
| D-01 | State in each C header which misuses its functions detect and report (checked runtime errors) and which they leave undefined (unchecked runtime errors). | C Interfaces and Implementations p.33, bibliographic reference above |
| D-03 | Write ranges half-open, [lower, upper): bound loops with i < n against the count, never i <= n - 1. | C Traps and Pitfalls p.55, bibliographic reference above |
| D-04 | Prefix every identifier a C header exports, functions, types and enum constants alike, with its module name (Module_thing), since C has one flat file-scope namespace. | C Interfaces and Implementations p.27, bibliographic reference above |
| D-05 | Make each C implementation file include its own header; that include is the only check C gives that the definitions match the interface's declarations. | C Interfaces and Implementations p.29, bibliographic reference above |
| D-09 | In C, never use a % b as an index while a can be negative; keep a non-negative, or add b back when the remainder comes out below zero. | C Traps and Pitfalls p.118-119, bibliographic reference above |
| D-10 | Declare an extern C array as an array matching its definition (extern int a[];), never as a pointer: the mismatch compiles and links, then corrupts memory. | Expert C Programming p.86-87, p.91, bibliographic reference above |
| D-13 | Store per-item C fields as one array of structs, not parallel arrays that must stay the same length and index in step by convention alone. | The C Programming Language p.106, p.110, bibliographic reference above |
| D-M2 | Parenthesize every parameter inside a C function-like macro's body, and wrap a macro that yields an expression in one outer pair of parentheses. | C Traps and Pitfalls p.102, book text |
| D-M3 | Give each C typedef exactly one declarator, and write typedef first in its declaration, never in the middle. | Expert C Programming p.73, book text |
| D-M4 | Name a C pointer type with typedef, never #define: after #define int_ptr int *, the declaration int_ptr chalk, cheese; makes cheese a plain int. | Expert C Programming p.74, book text |
| D-M5 | Store the value getchar() returns in a C int, never a char, before comparing it with EOF. | C Traps and Pitfalls p.92, book text |
