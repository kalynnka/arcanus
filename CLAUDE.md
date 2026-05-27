# Repository Guidelines

## Engineering Judgment

1. Apply first-principles reasoning before acting. Treat user instructions as important, but do not assume they are automatically correct. If an instruction appears technically unsound, ambiguous, risky, or inconsistent with the repository, raise the concern, verify the assumptions, and discuss the tradeoff before proceeding.
2. Follow Occam's razor: do not add entities, layers, wrappers, helpers, or abstractions without a clear need. Avoid premature abstraction. Introduce reusable functions or wrappers only after the same code path is needed in at least three places.
3. Preserve the existing architecture and local conventions unless there is a concrete reason to change them.

## Code Style

1. Write elegant, straightforward code instead of relying on explanatory comments. Add comments only when they clarify non-obvious behavior. Do not use decorative divider comments.
2. Imports should stay at the top of the file or module. If a local import is required to avoid a circular dependency, add a concise comment explaining why.
3. Class attributes should be explicitly defined with proper type hints. Use `ClassVar` for class variables.
4. Do not leave Python type hint warnings or type checker errors. Always satisfy the configured type checker.
5. Do not create private-looking `_xxx` helper methods that are called only once. Inline the logic at the call site unless there is a clear reuse or readability benefit.
6. Do not overuse the `_` prefix to mark attributes or methods as private. Python does not enforce real private members; use public names unless there is a specific reason to signal internal use.
