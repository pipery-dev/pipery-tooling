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

    cmd = ["argocd", "app", "sync", app]
    if strategy == "blue-green":
        cmd += ["--blue-green"]
    elif strategy == "canary":
        cmd += ["--canary-weight=10"]

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

    cmd = [
        "gcloud", "run", "deploy", service,
        "--image", image,
        "--region", region,
    ]
    if project:
        cmd += ["--project", project]

    return subprocess.run(cmd, check=False).returncode


# ---------------------------------------------------------------------------
# Helm
# ---------------------------------------------------------------------------

def _deploy_helm(strategy: str, cfg: dict[str, Any]) -> int:
    release = cfg.get("helm_release") or os.environ.get("HELM_RELEASE", "")
    chart = cfg.get("helm_chart") or os.environ.get("HELM_CHART", "")
    namespace = cfg.get("helm_namespace") or os.environ.get("HELM_NAMESPACE", "default")

    cmd = [
        "helm", "upgrade", "--install",
        release, chart,
        "-n", namespace,
    ]
    if strategy == "blue-green":
        cmd += ["--blue-green"]
    elif strategy == "canary":
        cmd += ["--canary-weight=10"]

    return subprocess.run(cmd, check=False).returncode


# ---------------------------------------------------------------------------
# Ansible
# ---------------------------------------------------------------------------

def _deploy_ansible(cfg: dict[str, Any]) -> int:
    playbook = cfg.get("ansible_playbook") or os.environ.get("ANSIBLE_PLAYBOOK", "")
    inventory = cfg.get("ansible_inventory") or os.environ.get("ANSIBLE_INVENTORY", "")

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
