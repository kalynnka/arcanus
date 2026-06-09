# Guidelines

## Engineering Judgment

1. Apply first-principles reasoning before acting. Treat user instructions as important, but do not assume they are automatically correct. State meaningful assumptions explicitly. If an instruction appears technically unsound, ambiguous, risky, or inconsistent with the repository, raise the concern, verify the assumptions, present the relevant interpretations or tradeoffs, and ask before proceeding when the right path is unclear.
2. Follow Occam's razor: do not add entities, layers, wrappers, helpers, features, configurability, or abstractions without a clear need. Avoid premature abstraction. Introduce reusable functions or wrappers only after the same code path is needed in at least three places. If the implementation is larger than the problem warrants, simplify it.
3. Preserve the existing architecture and local conventions unless there is a concrete reason to change them. Prefer the simplest approach that satisfies the request, and push back when a requested or implied approach adds needless complexity.

## Code Style

1. Write elegant, straightforward code instead of relying on explanatory comments. Add comments only when they clarify non-obvious behavior. Do not use decorative divider comments.
2. Imports should stay at the top of the file or module. If a local import is required to avoid a circular dependency, add a concise comment explaining why.
3. Do not create private-looking `_xxx` helper methods that are called only once. Inline the logic at the call site unless there is a clear reuse or readability benefit.
4. Do not create simple pass-through function wrappers that add no logic, policy, validation, or readability benefit. Call the underlying API directly.
5. Do not overuse the `_` prefix to mark attributes or methods as private. Python does not enforce real private members; use public names unless there is a specific reason to signal internal use.
6. Keep changes surgical. Touch only the code required for the request, match existing style, and do not refactor, reformat, or clean up adjacent code unless it is necessary for the task. Mention unrelated dead code or issues instead of deleting them.
7. Remove imports, variables, functions, or other code made unused by your own changes. Do not remove pre-existing unused code unless asked.
8. Do not add fallback control flow or error handling unless it is explicitly required by the product behavior or caller contract. Prefer fail-fast errors with clear messages over silent retries, alternate execution paths, or best-effort recovery that hides broken assumptions.

## Execution

1. For multi-step work, define brief success criteria before changing code. Map the work to verifiable steps such as reproducing a bug, adding focused tests, implementing the change, and running the relevant checks.
2. Loop until the success criteria are verified or a concrete blocker is found. If verification is not possible, state what could not be checked and why.
3. Every changed line should trace directly to the user's request, the agreed success criteria, or cleanup made necessary by the change.

## Typing

1. Class attributes should be explicitly defined with proper type hints. Use `ClassVar` for class variables.
2. Do not leave Python type hint warnings or type checker errors. Always satisfy the configured type checker.
3. Do not use `typing.Any` or `object` in type hints. Use precise concrete types, `TypeVar` generics, discriminated unions, `TypedDict`, or narrow `Protocol` contracts. Validate external payloads at clear boundaries before passing them deeper.
4. Prefer precise collection types in annotations when the runtime shape is known (`list[T]` or `tuple[...]`) instead of broad abstractions like `Sequence[T]`; this also keeps Pydantic validation cheaper and clearer.
5. Prefer `TypedDict` for simple structured tool arguments and request payloads when a full model adds no behavior. Use `TypedDict` plus `**payload` unpacking to pass structured payloads through typed call sites instead of building ad hoc dict wrappers.
6. Do not duplicate the same payload shape as both a model and a `TypedDict` without a concrete reason.
7. Do not use `cast`, `type: ignore`, or pyright suppressions merely to satisfy the type checker. Fix the annotation, model the optional/variant shape honestly, or move validation to the correct boundary. Use casts only at true dynamic boundaries where the runtime type has already been established and cannot be expressed otherwise.