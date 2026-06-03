---
name: spgr-write-iac
description: Write infrastructure as code that defines every cloud resource (networking, compute, data, secrets, IAM, observability) for dev, staging, and prod as reusable modules with environment-variable overrides, remote state, and CI validation, so any environment provisions, updates, and destroys reproducibly with no manual console changes. Use when the DevOps Agent must stand up or change cloud infrastructure from an approved infrastructure diagram, or when the Architect or Security Agent needs IaC produced against the confirmed topology and least-privilege IAM before a deploy proceeds.
---

# write-iac

## Purpose

Turn the approved infrastructure diagram into version-controlled, machine-executable cloud resource definitions. Manual console configuration produces snowflake environments whose state lives only in whoever clicked through the console, which causes drift incidents and slow disaster recovery. Make the desired state explicit, peer-reviewed, and reproducible so a new environment provisions in 30 minutes, not 3 days. This skill writes source files, not an envelope artifact. Verification is `terraform validate`, `tflint`, policy-as-code, and CI, not a content schema.

## Inputs

| Field | Description |
|-------|-------------|
| `infrastructure-diagram` | Approved by the Architect Agent. The source of truth for topology. Read via spgr-read-artifact. |
| `cloud-provider` | AWS, GCP, Azure, or multi-cloud. Sets the resource types and remote-state backend. |
| `service-requirements` | Per-environment compute sizing, database tier, cache tier, CDN, and networking topology. |
| `secrets-strategy` | Which secrets manager, naming conventions, and rotation policy. The IaC references secrets, it does not store values. |

## Outputs

| Artifact | Description |
|----------|-------------|
| IaC configuration | Terraform preferred. AWS CDK or Pulumi acceptable if the stack warrants it. Written via spgr-write-file. |
| Networking module | VPC, public and private subnets, routing, security groups, NAT gateway. |
| Compute module | Container cluster (ECS, EKS, Cloud Run, or equivalent), autoscaling, task or pod definitions referencing image tags from the artifact registry. |
| Data module | Managed database instance, read replicas if specified, connection pooler (PgBouncer or RDS Proxy), backup retention. |
| Secrets module | Secrets-manager references by ARN or name, IAM roles with least-privilege access policies. |
| Observability module | Log aggregation, metric exporter sidecars or agents, alerting channel connections. |
| Per-environment variables | dev, staging, prod share module code. Sizing and config are injected as variable overrides. |
| Remote state config | Terraform Cloud, or S3 plus DynamoDB locking, or equivalent. Access restricted by IAM. |

## Procedure

1. Read the infrastructure diagram via spgr-read-artifact and confirm the cloud provider, per-environment service requirements, and secrets strategy are all present. If the diagram is missing, unapproved, or contradicts the stated provider, stop and escalate via spgr-escalate rather than guessing topology.
2. Author each concern as a reusable module (networking, compute, data, secrets, observability). Modules are the unit of reuse. Do not copy-paste a per-environment stack, because environments then diverge silently. The per-environment root configuration instantiates modules with environment-specific variables.
3. Reference pre-existing resources (shared VPCs, DNS zones, certificate ARNs) through data sources, not hard-coded IDs. Hard-coded resource IDs break portability.
4. Reference every secret by ARN or secret name from the secrets manager. Never write a literal secret value into IaC code, a variable file, or a CI environment variable that appears in logs. The IaC configures which IAM roles read which secrets, nothing more.
5. Set per-environment sizing. dev is cheap: minimal instance sizes, single-AZ, no read replicas, smaller database tiers, since dev is for integration testing. staging mirrors production at production scale. production is production.
6. Configure remote state. Local state files are a coordination failure in a multi-agent environment, so use Terraform Cloud, or S3 with DynamoDB locking for AWS. State holds sensitive output values, so restrict access with IAM.
7. Write all files via spgr-write-file. Wire CI to run `terraform validate` and `tflint` on every IaC PR, and policy-as-code checks (Checkov or OPA Conftest) for compliance rules such as S3 buckets blocking public access and prod RDS instances having deletion protection enabled.
8. Add Infracost to the IaC PR so each PR comments with the estimated monthly cost delta, which stops a silent cost spike from landing.
9. Build ephemeral preview environments: for a feature branch with infrastructure changes, provision a short-lived environment from the IaC with a `-preview-<pr-number>` suffix, destroyed automatically when the PR merges or closes.
10. Add scheduled weekly drift detection: run `terraform plan` against each environment, and on detected drift alert the DevOps Agent immediately via spgr-notify-human.
11. Verify the output. Run `terraform validate` and `tflint` and confirm they pass before the change is handed off. Tag the Security Agent via spgr-tag-vertical-agent for review of any IAM policy or security-group change, and the Architect Agent for alignment with the diagram and ADRs. If validation fails or a least-privilege review cannot be satisfied within the approved topology, escalate via spgr-escalate rather than weakening a policy.
12. Record the provider, module structure, and remote-state backend choice with spgr-log-decision so the rationale is recoverable.

## Notes

- Output type is source or config (IaC files), not an envelope artifact. There is no registered content schema for IaC, so verification is `terraform validate`, `tflint`, policy-as-code, and CI rather than spgr-validate-artifact. If a decision summary is emitted as an artifact, spgr-validate-artifact applies envelope-only validation until a content schema is registered.
- No manual console changes, ever. If an emergency console change is made, codify it immediately and resolve the drift in the next deployment.
- DevOps enforces no literal secrets in any IaC file, tested rollback before a deploy is valid, and semantic versioning of module releases. Map these into every change.
- All infrastructure changes go through the same review as code: IaC PR with attached `terraform plan` output, Security Agent review for IAM changes, then apply through the CD pipeline.
