# Engineering Principles

## Purpose

This document defines the engineering principles and practices used to develop the Finance project.
The goal is not to maximize technical sophistication, but to build a useful, reliable, maintainable system through deliberate engineering decisions.

---

## Core Principles

### Correctness over cleverness

Prefer implementations that are correct, predictable, and easy to understand over solutions that are clever, highly optimized, or unnecessarily sophisticated.
A simple solution that can be readily verified is preferable to a more sophisticated solution whose behavior is harder to reason about.

### Prefer simplicity

Simple solutions are preferred unless additional complexity provides a demonstrated benefit. Complexity must earn its place.

### Avoid both over-engineering and under-engineering

Do not implement speculative functionality merely because it may be useful in the future.
Conversely, do not deliberately choose an obviously inadequate foundation simply to keep the initial implementation small.
When a capability is clearly necessary for the system to remain useful, maintainable, or scalable beyond a demonstration, it should be implemented when the relevant foundation is being built.
Defer functionality whose necessity depends on uncertain future requirements.
The goal is not minimal code. The goal is the simplest solution that is sufficient for the foreseeable requirements.

### Preserve optionality

Where practical, avoid decisions that unnecessarily constrain future evolution.
Do not implement hypothetical future requirements merely to preserve future options. Prefer designs that leave reasonable alternatives open when doing so has little or no additional cost.

### No premature abstraction, optimization, or generalization

* Do not introduce abstractions merely because multiple implementations might eventually exist.
* Do not optimize for performance characteristics that have not been demonstrated to be a problem.
* Do not generalize the data model or architecture to accommodate hypothetical future requirements.
* When a future requirement becomes real, prefer the simplest change that satisfies the demonstrated requirement.

### One fact, one place

Information should have one authoritative location. Other representations should reference or derive from that source rather than independently maintaining duplicate copies.
Different representations may legitimately exist when they serve different purposes, but their authority must remain clear.

### Make implicit knowledge explicit

Knowledge that is important to understanding, maintaining, or evolving the project should be captured explicitly rather than relying on assumptions, memory, or previous conversations.

Examples include:

* The rationale behind significant decisions.
* Architectural assumptions.
* Important constraints.
* Lessons from unexpected behavior.
* Known limitations and uncertainties.

### Preserve rationale

Knowing what was decided is often insufficient; understanding why it was decided is essential for future maintenance. Capture such decisions in DESIGN.md if it is related to the product being developed, 
and in ENGINEERING.md if it is related to the process of developing. 

### Separate intent from representation

The purpose of an artifact should be distinguished from the format or technology used to represent it.

For example:

* The purpose of the finance application is retrieving and persisting financial market data, not using progresql/timescaledb.
* A series is historical data to be preserved, not a particular database row structure.
* Markdown is a documentation format, not the documentation itself.
|
Implementation choices should serve the underlying intent and should remain replaceable where practical.

---

## Development Practices

### Incremental development

Build the system in small, coherent steps. Each change should provide a clear improvement or establish a well-defined foundation for future work.
Avoid implementing speculative functionality simply because it might become useful later.

### Engineering judgment over mechanical targets

Automated checks, thresholds, and metrics are safeguards that support engineering judgment; they are not substitutes for it.
A mechanically enforced target may be overridden when there is a sound engineering reason. Such exceptions must be deliberate, explicit, and documented at the appropriate level.
The rationale should explain why satisfying the mechanical target would be inappropriate or would make the design worse. Merely stating that an exception was necessary is insufficient.
Do not work around a metric or automated check simply to make it pass. When a target conflicts with a better design, preserve the better design and document the reasoning.

### Code explains how; tests and requirements explain what; comments explain why

The intended behavior of the system should be defined by requirements and acceptance tests. Tests should make the externally observable behavior explicit.
Code should express how that behavior is implemented and should be sufficiently clear to make its operation understandable without explanatory comments.

Comments should primarily explain why the code is structured or implemented in a particular way when that reason is not apparent from the code itself. 
They should capture deliberate engineering judgments, constraints, non-obvious trade-offs, or intentional deviations from an otherwise expected approach.
Do not use comments to restate what the code already makes clear.

### Acceptance-driven development

New behavior should have clear, externally observable acceptance criteria before implementation where practical.
Acceptance criteria should describe what the system must do rather than how it should implement it.
For significant behavior, acceptance criteria should normally be represented by automated tests.

### Tests are part of design

Tests are not an afterthought.

Tests should:

* Verify observable behavior.
* Provide rapid feedback.
* Protect against regression.
* Help expose misunderstandings in requirements.

Prefer tests that remain useful when implementation details change.

### Testability is a design signal

If behavior is unnecessarily difficult to test, first reconsider the design rather than adding test-specific machinery. Difficult testing often indicates implicit dependencies, excessive coupling, hidden state, or unclear boundaries.

### Coverage is a design signal

Test coverage is a quality signal, not an objective in itself. Uncovered code should prompt examination of whether:

* behavior is missing from the tests;
* the code represents an impossible or irrelevant state;
* the code is better exercised through an integration test;
* the code is unnecessary and should be removed; or
* the design can be simplified.

Tests must have a purpose beyond executing code. A test should normally verify behavior, expose a defect, or drive the design toward a defined requirement. Tests that merely execute code without asserting meaningful behavior should not be added solely to increase coverage.

Coverage measurements are a quality signal, not an absolute target. Integration tests that execute separate processes may exercise code that is not included in the unit-test coverage measurement.

### Static analysis findings are a design signal

Static analysis findings should be treated as indicators for engineering review, not merely lint violations to suppress.

In particular:

* High cyclomatic complexity may indicate excessive branching, too many responsibilities, or an unclear abstraction boundary.
* Excessive function arguments may indicate that responsibilities or related state have not been modeled appropriately.
* Excessive branching, nesting, or other complexity metrics may indicate similar design problems.

Where practical, these constraints should be enforced automatically through the project's static analysis tooling rather than relying on manual review.

### Prefer explicit test dependencies

Tests should prefer explicit dependency injection and controlled inputs over modifying global state. Pytest monkeypatch should not be used unless there is no reasonable explicit alternative.

### Documentation follows the work

Documentation should be created or updated as part of the engineering work that produces the knowledge it describes.
Do not defer important documentation until the end of a project or feature.
Documentation should remain lightweight enough that maintaining it is practical.

### Automate repetitive engineering work

Automate repetitive validation and maintenance activities where the cost of automation is justified. Examples include:

* Test execution.
* Linting.
* Documentation validation.
* Database schema validation.
* Search performance measurements.

Automation should reduce the cost of good engineering practices rather than become an additional burden.

### Make decisions reversible where practical

When uncertainty exists, prefer approaches that allow learning and change.
Small experiments are preferred over large irreversible commitments when the uncertainty is significant.
Irreversible decisions should have stronger justification than easily replaceable implementation choices.

### Use explicit data models

Use dataclasses for application-domain objects where they provide a clear representation of structured data.
Prefer explicit, typed models over unstructured dictionaries when an object has a defined meaning within the application.
Keep domain models independent of persistence details where practical.

---

## Dependencies

### External dependencies must earn their place

Every external dependency (e.g. a library) introduces maintenance, security, compatibility, and reproducibility costs.
Before proposing a dependency, determine whether the requirement can reasonably be satisfied by the standard library or an existing dependency.
A dependency should solve a real problem rather than merely make a small piece of code more convenient.

### Dependency injection

Dependencies are explicit; composition is centralized.

Prefer dependency injection through ordinary language mechanisms such as function parameters, constructors, and factories. A dependency-injection framework is not required unless the problem genuinely warrants one.
Service locators are prohibited because they hide dependencies and tend to create centralized objects with excessive responsibility.

### Composition belongs at the boundary

Construction of concrete infrastructure dependencies should occur at the application's composition root.
Application and domain code should receive their dependencies rather than discovering or constructing them internally.
This keeps infrastructure choices out of business logic and makes dependencies explicit and replaceable.

### New libraries require explicit approval

Introducing a new library requires explicit human approval.
An agent must not add a new dependency to the project, modify dependency manifests to introduce it, or otherwise make it a project dependency before approval is given.

An approval request must provide sufficient evidence to evaluate the choice, including where relevant:

* Why the dependency is needed.
* Why the standard library or existing dependencies are insufficient.
* Alternatives considered and why they were rejected.
* Project health and maintenance activity.
* Runtime and Python compatibility.
* License and legal compatibility.
* Security and supply-chain considerations.
* Proposed version and rationale.
* Expected scope of use.

The evidence should come from current, authoritative sources where practical.

Approval applies to the specific dependency and proposed use. A materially different version or role requires renewed approval.

### License compatibility

Project and dependency licenses must be explicitly checked before introducing a dependency.
Do not assume that a library is compatible with the project merely because it is popular, widely used, or available through a package repository.

The project's license is defined by `LICENSE`.

---

## Repository Conventions


### Work tracking

GitHub Issues are the authoritative backlog for planned, proposed, and tracked work. Do not maintain a parallel backlog in repository documentation.

### File naming

Use conventional names for well-known repository files such as `README.md`, `LICENSE`, and `AGENTS.md`.

Use kebab-case for human-facing documentation where practical.

Use snake_case for Python source and test modules.

### Test naming

Test modules should normally correspond directly to the production module they test, using the `test_<module>.py` convention. 
If multiple test modules are needed for a single production module, creating a subfolder with the module name to store those test modules in is recommended. Naming should then be `test_<topic>.py`.

Integration tests spanning multiple production modules may use a descriptive name when there is no single natural production-module counterpart.

### Documentation structure

Project documentation belongs in the repository and should be discoverable through the repository structure.

Engineering principles and practices belong in this document.

Do not duplicate authoritative content across these documents merely for convenience.

### Diagrams

Use Mermaid for architecture diagrams where practical.

Diagrams should communicate:

* Responsibilities.
* Boundaries.
* Relationships.
* Information flow.

Avoid unnecessary implementation detail and avoid duplicating information that is already authoritative elsewhere.


## Test design principles

Tests should focus on external behavior, not internal implementation details. The exception to this rule are tests for main() and Orchestrator. 
Tests for these are deliberately integration-focused due to their role as system level coordinators. 

---
