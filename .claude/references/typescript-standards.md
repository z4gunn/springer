# TypeScript standards (shared)

The single source of truth for every line of JavaScript-runtime code a Springer agent generates: web frontends, Node services, React Native and Expo mobile apps, generated SDKs, test suites, and project scaffolds. Each skill and agent that writes, lints, formats, gates, or chooses the language for such code references this file by absolute path and adds no duplicate rules. The rules here do not apply to non-JS languages such as Python, Go, Swift, or Kotlin, which keep their own stack-default tooling.

## Contents
- Language mandate
- Baseline tooling
- Compiler configuration
- Formatting
- Linting
- Type-safety rules
- Naming conventions
- Enforcement split
- Boundaries

## Language mandate

TypeScript is mandatory for every JavaScript-runtime stack. A project that runs on Node, a browser, or a JS-based mobile runtime is written in TypeScript, never plain JavaScript. New `.js` and `.jsx` source files are not permitted. Use `.ts` and `.tsx` only. Configuration files that a tool requires in JavaScript form (for example `eslint.config.js` or a bundler config) and machine-generated output are the only exceptions.

This is a hard rule. An agent that cannot satisfy a requirement in TypeScript within the approved architecture raises spgr-escalate rather than falling back to plain JavaScript. The tech-stack-decision cannot record plain JavaScript as a language layer.

## Baseline tooling

New TypeScript projects are initialized with Google's gts through `npx gts init`. gts installs three things the project then extends:
- `tsconfig.json` extending the gts `tsconfig-google.json` strict base.
- An ESLint flat config (`eslint.config.js`) built on typescript-eslint and eslint-config-prettier.
- A `.prettierrc.json` carrying the gts formatting defaults.

The project does not replace these files. It extends the gts tsconfig, extends the gts ESLint config with the Springer overrides below, and keeps the gts Prettier config as committed. gts owns the baseline. Springer adds only the deltas recorded in this file.

## Compiler configuration

Inherit the gts strict base and require these compiler options explicitly in the project `tsconfig.json`:
- `strict: true`, which turns on `noImplicitAny`, `strictNullChecks`, `strictFunctionTypes`, `strictBindCallApply`, `strictPropertyInitialization`, `noImplicitThis`, and `useUnknownInCatchVariables`.
- `noImplicitReturns: true`
- `noFallthroughCasesInSwitch: true`
- `forceConsistentCasingInFileNames: true`
- `noUnusedLocals: true`
- `noUnusedParameters: true`
- `noEmitOnError: true`

A type error is a build failure. `tsc --noEmit` runs as a dedicated CI stage and blocks merge on any error. See spgr-write-ci-pipeline for the stage definition.

## Formatting

Formatting comes from the gts Prettier config, applied by spgr-format-code. The committed `.prettierrc.json` carries these gts defaults:
- `bracketSpacing: false`
- `singleQuote: true`
- `trailingComma: "all"`
- `arrowParens: "avoid"`

The formatter is the only authority on whitespace and layout. Never hand-edit formatted output to override style. If the output is wrong, the fix is in the config, not the file. The config is committed and the formatter version is pinned so an upgrade does not churn diffs. spgr-format-code owns formatter execution and the pre-commit hook.

## Linting

ESLint runs the gts base (typescript-eslint plus eslint-config-prettier) with these Springer overrides layered on top:
- `@typescript-eslint/no-floating-promises` at error. Every promise is awaited, returned, or explicitly voided.
- `import/order` enforcing grouped and alphabetized imports (builtin, external, internal, parent, sibling).
- `@typescript-eslint/naming-convention` encoding the naming rules below where a rule can express them.
- `eslint-plugin-security` stays active, as required by spgr-lint-code, so vulnerability patterns are caught in the same pass.

Do not add a rule suppression without an adjacent code comment that states the reason. A bare `// eslint-disable-next-line` is a violation to flag, not a fix to apply. spgr-lint-code owns lint execution and auto-fix.

## Type-safety rules

These rules require judgment and are checked in review where a linter cannot enforce them. They are drawn from the AWS CDK TypeScript guidance and the TypeScript handbook declaration do's and don'ts.

1. Do not use `any`. Use `unknown` when the type is genuinely not known or when a value passes through untouched, then narrow before use.
2. Use the primitive types `string`, `number`, `boolean`, and `symbol`, never the boxed `String`, `Number`, `Boolean`, or `Symbol`. Use `object` for a non-primitive, never `Object`.
3. Type a callback whose return value is ignored as `() => void`, not `() => any`, so callers may return anything without a type error.
4. Prefer a union type over overloads that differ in only one argument position. Prefer optional parameters over overloads that differ only in trailing arguments. When overloads are genuinely needed, order them specific signature first and general signature last.
5. Mark a property `readonly` when it is set only at construction. Reach for the standard utility types (`Partial`, `Required`, `Readonly`, `Pick`, `Omit`, `Record`) before hand-rolling a variant of an existing type.
6. Use `interface` for an object or contract shape. Do not declare an empty interface, which enforces no contract. Extend a base interface rather than copying its members.
7. Declare variables with `const` or `let`, never `var`. Prefer destructuring when pulling several fields from an object. Represent a fixed set of values with a string-literal union or an `enum`, and apply the chosen form consistently within a project.

## Naming conventions

- `camelCase` for variables, functions, and interface or type members.
- `PascalCase` for classes, interfaces, types, and enums.
- `UPPER_CASE` for global compile-time constants.
- File names in `kebab-case`, for example `ebs-volumes.ts`. A file whose default export is a React or Vue component uses `PascalCase` to match the component name, for example `UserCard.tsx`.

The `@typescript-eslint/naming-convention` rule enforces the identifier cases. File naming and semantic quality of names are reviewer judgment, checked by spgr-check-style-compliance.

## Enforcement split

| Concern | Enforced by |
|---------|-------------|
| Compiler strictness, no implicit any, null safety, unused code | `tsc --noEmit` |
| Whitespace, quotes, trailing commas, arrow parens, layout | Prettier |
| No floating promises, import order, identifier case, no `any`, security patterns | ESLint |
| Boxed vs primitive types, void callbacks, overload ordering, readonly intent, empty interfaces, utility-type reuse | reviewer judgment (spgr-check-style-compliance) |
| File naming, comment quality, semantic name choice, project idioms | reviewer judgment (spgr-check-style-compliance) |

## Boundaries
- spgr-format-code owns formatter execution and the pre-commit hook.
- spgr-lint-code owns lint execution and auto-fix.
- spgr-check-style-compliance owns the non-automatable residue: naming quality, comments, and idioms.
- This reference owns the required configuration and the language mandate.
- spgr-write-tech-stack-decision and spgr-scaffold-project apply the mandate and the gts baseline at project setup.
- spgr-write-ci-pipeline owns the typecheck, lint, and format CI gates that enforce this file on every merge.
