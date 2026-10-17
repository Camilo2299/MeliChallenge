"""Check high-impact IAM boundaries without contacting AWS."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "iac" / "identity"
for name in ("publish", "plan", "terraform"):
    for policy in json.loads((root / f"{name}.policy.json").read_text()):
        assert len(json.dumps(policy, separators=(",", ":"))) <= 6144
        for statement in policy["Statement"]:
            actions = statement["Action"]
            assert not any("*" in action for action in actions), actions
            if "iam:PassRole" in actions:
                assert set(statement["Resource"]) == {
                    "arn:aws:iam::026249143093:role/infra-signal-lab-execution",
                    "arn:aws:iam::026249143093:role/infra-signal-lab-task",
                }
                assert statement["Condition"]["StringEquals"]["iam:PassedToService"] == "ecs-tasks.amazonaws.com"
            if name == "publish":
                assert all(action.startswith("ecr:") for action in actions)
            if name == "plan":
                for action in actions:
                    if action in ("s3:PutObject", "s3:DeleteObject"):
                        assert all(resource.endswith("lab.tfstate.tflock") for resource in statement["Resource"])
                    else:
                        assert action == "apigateway:GET" or action.split(":")[1].startswith(("Get", "Describe", "List")), action
print("PASS: policy sizes, publisher scope, read-only planning and bounded PassRole")

foundation = json.loads((root.parent / "control" / "foundation.policy.json").read_text())
assert len(json.dumps(foundation, separators=(",", ":"))) <= 6144
for statement in foundation["Statement"]:
    assert all("*" not in action for action in statement["Action"])
    assert "iam:PassRole" not in statement["Action"]
    assert "iam:DeleteRolePermissionsBoundary" not in statement["Action"]
    if any(action.startswith("iam:") and not action.split(":")[1].startswith(("Get", "List")) for action in statement["Action"]):
        assert not any("foundation" in resource or "ceiling" in resource or "runtime-boundary" in resource for resource in statement["Resource"])
print("PASS: foundation policy cannot pass roles, remove boundaries, or modify control roles/policies")
