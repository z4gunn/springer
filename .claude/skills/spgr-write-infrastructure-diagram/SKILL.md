---
name: spgr-write-infrastructure-diagram
description: Produce an infrastructure-diagram artifact that maps the cloud topology to the IaC configuration, covering provider and regions, compute and managed services, VPC and subnet networking, CDN, load balancers, DNS, and summary IAM, with public-facing surfaces and environment boundaries marked explicitly. Use when the Architect Agent has an approved architecture option, deployment targets, and a cloud provider selection and needs the authoritative deployment-and-networking reference, or when the DevOps Agent must document or update the topology so the diagram stays in sync with the IaC.
---

# write-infrastructure-diagram

## Purpose

Turn an approved architecture option and its cloud provider selection into an infrastructure-diagram artifact that matches the IaC configuration line for line. The diagram is the authoritative reference for how the system is deployed and networked, and it makes the topology legible to every contributor, not only the engineer who built it. The contract here is that the diagram tracks the IaC, that environment boundaries are visually distinct, and that every surface reachable from the public internet is marked. A diagram that drifts from the IaC is worse than no diagram, because it misleads incident response, audits, and change review.

## Inputs

| Field | Description |
|-------|-------------|
| `architecture_option` | The approved architecture option that the topology realizes |
| `cloud_provider` | The selected cloud provider, for example AWS, GCP, or Azure |
| `deployment_targets` | The environments to represent, for example dev, staging, production |
| `iac_source` | The IaC configuration the diagram must match, for example Terraform or CDK, when available |

## Outputs

| Artifact | Description |
|----------|-------------|
| `infrastructure-diagram` | Topology artifact covering cloud provider and active regions, compute and managed services, VPC and subnet networking with public and private visibility, security group summaries, CDN and origin, load balancers and target groups, DNS, summary IAM roles and trust relationships, environment boundaries, and an explicit list of public-facing surfaces, with a Mermaid topology source |

## Procedure

1. Read the approved architecture option and the cloud provider selection. Read the IaC source if one exists. Use spgr-read-artifact for the architecture option and spgr-read-file for the IaC, so the topology is grounded in what is actually deployed rather than in intent.
2. Map the topology into the diagram content sections: cloud provider and active regions, services used (compute, managed databases, cache, object storage, queues, functions), networking (VPC, subnets marked public or private, security groups, NACLs), CDN and its origin, load balancers and target groups, DNS, and summary-level IAM roles with trust relationships. Summarize security group rules at the diagram level and leave the full rules in the IaC.
3. Place all compute and database resources in private subnets unless the architecture states an explicit requirement for public access. Mark every public-facing surface explicitly in the `public_facing_surfaces` list so anything reachable from the public internet is obvious.
4. Show environment boundaries clearly. Represent dev, staging, and production as visually distinct groupings in the Mermaid source so a reader cannot confuse one environment for another.
5. Write the Mermaid topology source. Group nodes by environment and by subnet visibility, label public-facing edges, and keep the diagram aligned with the IaC. When the IaC supports diagram generation from config (for example a Terraform or CDK graph), prefer the generated topology as the starting point to keep diagram and config in sync, then annotate it.
6. Produce the artifact with spgr-write-artifact, which stamps the shared envelope, records per-section confidence, initializes the decision log, and runs spgr-validate-artifact against the registered infrastructure-diagram schema inline before write. Do not hand-build the envelope.
7. Consult the Security Agent through spgr-tag-vertical-agent on the networking and public-facing-surface sections before the diagram is finalized, since exposure and isolation decisions are in the Security vertical's domain.
8. If the IaC and the architecture option disagree, if the cloud provider or deployment targets are missing, or if a resource cannot be placed without an undocumented public-access decision, stop and raise spgr-escalate with a precise list of what is missing or conflicting rather than inventing a topology.
9. Log any consequential topology choice, for example a resource placed in a public subnet or a region selection, with spgr-log-decision so the reasoning is traceable.

## Notes

- The infrastructure-diagram artifact type is registered in the schema registry at `/Users/gunderer/Repos/springer/schemas/` as `infrastructure-diagram-v1.json`. Reference field requirements through spgr-validate-artifact rather than inlining them here.
- The diagram must match the IaC. When the IaC changes, update the diagram in the same commit through spgr-version-artifact so the two never drift apart.
- A network flow diagram showing ingress and egress rules supports compliance documentation and can be added as a second Mermaid view in the same artifact when a compliance framework requires it.
