# iOS native-harness integrity gate

Apply this gate whenever the task is labeled iOS, uses Apple frameworks, includes an Xcode project/workspace, imports XCTest/XCUITest, uses `environment: mac_swe`, or carries iOS/macOS-VM routing tags.

## Route first

Resolve whether the task is iOS T-Bench or iOS SWE-Bench from `task.toml` and repository/template metadata. Do not infer the track from Swift files alone.

After the generic per-track reviewer, run the current `team-aai:aai-ios review` lens. The generic reviewer owns severity and the final decision; this gate supplies an iOS-specific blocking finding.

## Required execution shape

For an iOS SWE-Bench task, require evidence that:

- it lives in the dedicated iOS SWE-Bench track/repository shape rather than being labeled iOS inside an unrelated generic repository;
- the source is a real repository pinned at a base commit;
- the supported iOS project shape is built on the shared macOS-VM infrastructure (`mac_swe`, SandoQ, or the current successor);
- the grader executes the real target with XCTest/XCUITest or the current supported native test runner;
- `fail_to_pass` tests fail on the untouched base and pass after the gold fix;
- `pass_to_pass` exercises the real existing regression suite;
- hidden tests are injected at grade time and assertions check observable behavior;
- oracle is reproducibly 1.0 and nop/base is 0.0 for the intended behavioral reason.

Use current `aai-ios` and template guidance because supported project shapes and exact commands can change.

## Blocking anti-pattern: regex-rehosted Swift

Default to a blocking **Request changes** finding when the primary grader:

1. uses regex or text slicing to extract methods, declarations, or source fragments from Swift production files;
2. pastes or rewrites those fragments into a dummy shell, mock class, synthetic executable, or surrogate source file; and
3. grades that surrogate instead of compiling and executing the actual submitted iOS target through the supported harness.

This does not validate the shipped code. It can miss compilation and linkage failures, target membership, imports, access control, protocol conformance, actor isolation, lifecycle behavior, Apple-framework semantics, generated-project configuration, real consumers, and regressions outside the extracted fragment. It also overfits grading to source shape rather than observable behavior.

Classify it under the canonical per-track reward-integrity or environment-broken bucket. Recommend High unless the current rubric requires a stronger classification. The operational decision is **Request changes**, not Reject, because the author can migrate the task to the supported harness and rebuild the tests.

## What is and is not allowed

Allowed:

- regex used only to parse native test-runner output into the required result schema;
- static source checks as a supplemental guard when native behavioral tests remain the authoritative grade;
- a genuinely cross-platform Swift package tested by compiling and running its real SwiftPM/XCTest targets in a non-iOS track, provided the task is not represented or scored as iOS.

Not allowed as the primary grade for an iOS task:

- source-text assertions that substitute for execution;
- extracting a method and compiling it outside its actual type/module;
- dummy classes that recreate only the expected dependencies;
- shell or Python translations of Swift behavior;
- synthetic tests that never build or run the submitted app/library target.

## Current-task checks

Before filing the blocker, cite current-task evidence for all of these:

- repository/track mismatch, if present;
- exact extraction regexes and source files;
- generated dummy/shell class or surrogate target;
- the command the verifier actually executes;
- absence of a native build/test command against the submitted target;
- which real integration or regression surfaces are therefore unmeasured.

Do not cite another task as precedent in the author-facing review.

## Preferred concise author-facing message

When this is the only blocker, use this exact wording:

```text
This task needs to be resubmitted using the iOS swebench framework so it can be built with Xcode and tested using XCTest. The correct template to use is https://github.com/codimango/ios-swe-bench-template.
```

Do not add comparisons, precedent tasks, reviewer process, or a longer technical explanation unless another current-task blocker needs its own evidence.

## Detailed paste-ready finding shape

Use the longer form only when the review needs to explain why the current verifier is invalid:

```text
The verifier does not execute the submitted iOS target (High - reward integrity). It extracts Swift source fragments and runs them in a synthetic shell, so a passing reward does not prove that the real target compiles, links, integrates with its consumers, or behaves correctly under XCTest/XCUITest. Move the task to the supported iOS SWE-Bench harness and grade the actual target with native fail-to-pass and pass-to-pass tests. Fixed when the untouched base fails the intended native test, the gold fix passes it, the existing regression suite remains green, and the oracle/nop runs are reproducible on the macOS-VM backend.
```

## Sources to re-check for freshness

- `fbcode/claude-templates/components/plugins/team-aai/skills/aai-ios/review.md`
- `fbcode/claude-templates/components/plugins/team-aai/skills/aai-ios/tracks/swebench.md`
- `fbcode/claude-templates/components/plugins/team-aai/skills/aai-ios/tracks/vet.md`
- AAI Task Authoring Guide: iOS
