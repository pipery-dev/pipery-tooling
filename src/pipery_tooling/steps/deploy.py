from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


try:
    import yaml as _yaml  # type: ignore[import-untyped]
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


def run(
    target: str,
    strategy: str,
    log_file: str,
    config_file: str | None = None,
    **kwargs: Any,
) -> int:
    """Deploy using *target* backend with *strategy*.

    If *config_file* is provided its YAML contents are merged with *kwargs*
    (kwargs take precedence).  Supported targets: argocd, cloud-run, helm,
    ansible.

    Returns 0 on success, 1 on failure.
    """
    cfg: dict[str, Any] = {}
    if config_file:
        cfg = _load_yaml(config_file)
    cfg.update(kwargs)

    try:
        rc = _dispatch(target, strategy, cfg)
    except Exception as exc:
        print(f"Deploy error: {exc}", file=sys.stderr)
        _write_log(log_file, target, strategy, "failure")
        return 1

    status = "success" if rc == 0 else "failure"
    _write_log(log_file, target, strategy, status)
    return rc


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _dispatch(target: str, strategy: str, cfg: dict[str, Any]) -> int:
    if target == "argocd":
        return _deploy_argocd(strategy, cfg)
    if target == "cloud-run":
        return _deploy_cloud_run(strategy, cfg)
    if target == "helm":
        return _deploy_helm(strategy, cfg)
    if target == "ansible":
        return _deploy_ansible(cfg)
    raise ValueError(f"Unsupported deploy target: {target!r}")


# ---------------------------------------------------------------------------
# ArgoCD
# ---------------------------------------------------------------------------

def _deploy_argocd(strategy: str, cfg: dict[str, Any]) -> int:
    server = cfg.get("argocd_server") or os.environ.get("ARGOCD_SERVER", "")
    app = cfg.get("argocd_app") or os.environ.get("ARGOCD_APP", "")
    token = cfg.get("argocd_auth_token") or os.environ.get("ARGOCD_AUTH_TOKEN", "")

    if not app:
        print("Error: argocd_app / ARGOCD_APP is required", file=sys.stderr)
        return 1

    # Blue-green and canary strategies for ArgoCD are configured in the
    # Application spec (via Argo Rollouts), not as CLI sync flags.
    if strategy in ("blue-green", "canary"):
        print(f"Note: '{strategy}' strategy for ArgoCD is managed via Argo Rollouts "
              "in the Application spec; running plain sync.")

    cmd = ["argocd", "app", "sync", app]
    env = dict(os.environ)
    if server:
        env["ARGOCD_SERVER"] = server
    if token:
        env["ARGOCD_AUTH_TOKEN"] = token

    return subprocess.run(cmd, env=env, check=False).returncode


# ---------------------------------------------------------------------------
# Cloud Run
# ---------------------------------------------------------------------------

def _deploy_cloud_run(strategy: str, cfg: dict[str, Any]) -> int:
    project = cfg.get("cloudsdk_core_project") or os.environ.get("CLOUDSDK_CORE_PROJECT", "")
    service = cfg.get("cloud_run_service") or os.environ.get("CLOUD_RUN_SERVICE", "")
    image = cfg.get("cloud_run_image") or os.environ.get("CLOUD_RUN_IMAGE", "")
    region = cfg.get("cloud_run_region") or os.environ.get("CLOUD_RUN_REGION", "us-central1")

    if not service:
        print("Error: cloud_run_service / CLOUD_RUN_SERVICE is required", file=sys.stderr)
        return 1
    if not image:
        print("Error: cloud_run_image / CLOUD_RUN_IMAGE is required", file=sys.stderr)
        return 1

    cmd = [
        "gcloud", "run", "deploy", service,
        "--image", image,
        "--region", region,
    ]
    if project:
        cmd += ["--project", project]
    # Cloud Run traffic splitting handles blue-green and canary natively
    if strategy == "canary":
        cmd += ["--no-traffic"]  # deploy new revision without routing traffic yet
    elif strategy == "blue-green":
        cmd += ["--no-traffic"]  # caller manages traffic split separately

    return subprocess.run(cmd, check=False).returncode


# ---------------------------------------------------------------------------
# Helm
# ---------------------------------------------------------------------------

def _deploy_helm(strategy: str, cfg: dict[str, Any]) -> int:
    release = cfg.get("helm_release") or os.environ.get("HELM_RELEASE", "")
    chart = cfg.get("helm_chart") or os.environ.get("HELM_CHART", "")
    namespace = cfg.get("helm_namespace") or os.environ.get("HELM_NAMESPACE", "default")
    values_file = cfg.get("helm_values_file") or os.environ.get("HELM_VALUES_FILE", "")

    if not release:
        print("Error: helm_release / HELM_RELEASE is required", file=sys.stderr)
        return 1
    if not chart:
        print("Error: helm_chart / HELM_CHART is required", file=sys.stderr)
        return 1

    # Blue-green/canary for Helm require plugins (e.g. Argo Rollouts or Flagger).
    # Plain upgrade is used here; the caller configures the rollout strategy
    # via chart values.
    if strategy in ("blue-green", "canary"):
        print(f"Note: '{strategy}' strategy for Helm is managed via chart values "
              "or a rollout controller (e.g. Argo Rollouts); running plain upgrade.")

    cmd = [
        "helm", "upgrade", "--install",
        release, chart,
        "-n", namespace,
    ]
    if values_file:
        cmd += ["-f", values_file]

    return subprocess.run(cmd, check=False).returncode


# ---------------------------------------------------------------------------
# Ansible
# ---------------------------------------------------------------------------

def _deploy_ansible(cfg: dict[str, Any]) -> int:
    playbook = cfg.get("ansible_playbook") or os.environ.get("ANSIBLE_PLAYBOOK", "")
    inventory = cfg.get("ansible_inventory") or os.environ.get("ANSIBLE_INVENTORY", "")

    if not playbook:
        print("Error: ansible_playbook / ANSIBLE_PLAYBOOK is required", file=sys.stderr)
        return 1

    cmd = ["ansible-playbook", playbook]
    if inventory:
        cmd += ["-i", inventory]

    return subprocess.run(cmd, check=False).returncode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml(config_file: str) -> dict[str, Any]:
    if not _YAML_AVAILABLE:
        raise ImportError("pyyaml is required to use --config-file")
    with open(config_file, encoding="utf-8") as fh:
        data = _yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _write_log(log_file: str, target: str, strategy: str, status: str) -> None:
    entry = json.dumps(
        {"event": "deploy", "status": status, "target": target, "strategy": strategy}
    )
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError as exc:
        print(f"Warning: could not write log entry: {exc}", file=sys.stderr)
