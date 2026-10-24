---
name: spgr-check-buildability
description: Produce a buildability-check artifact that reads the proposed PRD, backlog, and NFR as the developer who will build first, and sorts every question that builder would ask into answered, minor, or human. Use before the first requirements gate so the human sees only the questions that need them.
disable-model-invocation: true
---

# check-buildability

## Purpose

An author reads their own requirements and finds them complete. The builder who receives them finds the gaps on the first day of work, and each gap then costs an escalation, a gate, or a guess. This skill moves that day forward: the developer agent that will build first reads the proposed requirements before the first gate, cold, as the builder, and lists every question it would have to ask. Each question lands in one pile. Answered questions cite where the artifacts settle them and go no further. Minor ones become defaults the run takes and lists. Only the human pile reaches the gate, so the human answers in one sitting the questions that would otherwise interrupt the build one at a time.

## Inputs

| Field | Description |
|-------|-------------|
| `prd_ref` | The proposed PRD, read with spgr-read-artifact |
| `backlog_ref` | The proposed prioritized backlog and its stories |
| `nfr_ref` | The proposed NFR spec, when the profile writes one |
| `builder_agent` | The agent reading as the builder: the Frontend Developer for a profile with a UI, the Backend Developer for `api` |
| `decision_classes` | Decision classes and the defaults ledger in `.claude/references/pdca-harness.md` |

## Outputs

| Artifact | Description |
|----------|-------------|
| `buildability-check` | Envelope artifact validated against the registered `buildability-check` schema: the refs read and every question with its pile, consumer, and the citation, default, or recommended answer its pile requires |

## Procedure

1. Read the PRD, the backlog, and the NFR with spgr-read-artifact. Read nothing the builder would not be handed: no discovery corpus, no architecture options. Architecture questions belong to the Architect, and the options are written in the same batch.
2. Walk the first stories the walking skeleton or the first batch would build, end to end, as if starting the code now: the screens or endpoints, the data each one needs, the states, the copy, the integrations, the deploy target, and the access the build needs. Write down every point where you would stop and ask.
3. For each question, search the three artifacts for the answer. A question the artifacts settle goes in `answered` with the artifact id and section. Do not pile a question as answered on an inference the text does not state.
4. Sort what remains by the decision classes. A reversible decision inside the profile goes in `minor` with the recommended default the build will take. A blocking decision, or a fact only the human holds (content, brand, accounts, credentials, a deploy target), goes in `human` with the recommended answer the gate offers first and its decision class. A missing fact is never invented. Its default is a visible placeholder.
5. Merge duplicates and drop any question that is already an open question in the PRD, citing it instead.
6. Write the artifact with spgr-write-artifact and validate it inline with spgr-validate-artifact. Write no code and open no branch. Record the sort of any question close to the line between minor and human with spgr-log-decision.

## Notes

- The harness turns the piles into run state: each `minor` question becomes a defaults-ledger line, each `human` question joins the decisions of the first gate that carries the requirements, and `answered` questions go nowhere.
- A long human pile is a finding about the requirements, not a failure of this skill. Report it as it stands.
- This skill has no Phase 1 vault spec. It was authored to the Springer build standards as a net-new capability.
