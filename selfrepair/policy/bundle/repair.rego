# OPA Rego policies for the SelfRepair repair pipeline.
#
# This bundle is the future migration target for the engine in
# `selfrepair/policy/engine.py`. The Python engine and these Rego rules
# implement the same logic; we'll migrate the runtime to OPA when:
#   - we have a sidecar deployment (Helm chart with the OPA service);
#   - we need policy-as-data shared across services;
#   - customers ask for the ability to write their own Rego.
#
# Until then this file is documentation and ground truth: each rule below
# mirrors a Python rule in selfrepair/policy/rules/.

package selfrepair.repair

import future.keywords.if
import future.keywords.in

# Default: allow only when no rule says otherwise.
default decision := {"outcome": "allow", "rule_id": "default"}

# Deny when a touched path matches a deny_paths pattern.
decision := {
  "outcome": "deny",
  "rule_id": "deny_paths",
  "reason": reason,
} if {
  some path in input.files_changed
  some pattern in input.repo_config.deny_paths
  glob.match(pattern, ["/"], path)
  reason := sprintf("path %q matches deny pattern %q", [path, pattern])
}

# Deny LLM repair without explicit opt-in.
decision := {
  "outcome": "deny",
  "rule_id": "risk.llm_not_opted_in",
  "reason": "LLM repair attempted but repo has not opted in via escalate_to_llm",
} if {
  input.is_llm_repair
  not opted_in
}

opted_in if {
  some rule in input.repo_config.escalate_to_llm
  rule.kind == input.finding.kind
}

# Require review for high or critical risk.
decision := {
  "outcome": "review",
  "rule_id": "risk.high",
  "requires_approval": true,
  "reason": sprintf("plan.risk = %q requires human approval", [input.plan.risk]),
} if {
  input.plan.risk in {"high", "critical"}
}

# Require review when codeowners_required is set and any file changed.
decision := {
  "outcome": "review",
  "rule_id": "codeowners.required",
  "requires_approval": true,
} if {
  input.repo_config.codeowners_required == true
  count(input.files_changed) > 0
}
