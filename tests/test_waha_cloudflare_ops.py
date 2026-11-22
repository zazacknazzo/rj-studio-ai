"""Operator tooling invariants; no Cloudflare or WhatsApp calls."""

from types import SimpleNamespace

import pytest

from rj_studio_ai import waha_cloudflare_ops as ops
from rj_studio_ai.waha_authority import AuthorityClosed
from rj_studio_ai.waha_cloudflare import create_waha_cloudflare_app


def test_deployment_receipt_blocks_mutation_before_contacting_cloudflare(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "PRIVATE", tmp_path)
    ops.private_write(tmp_path / "authority.wrangler.json", {"name": "fixture"})
    ops.private_write(tmp_path / "authority.deploy-log.json", {"exit_code": 1})

    def forbidden(*args):
        pytest.fail("must reconcile previous deployment before another mutation")

    monkeypatch.setattr(ops, "wrangler", forbidden)
    with pytest.raises(ValueError, match="deployment_receipt_exists"):
        ops.deploy("authority")


def test_deployment_receipt_never_records_raw_output_or_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "PRIVATE", tmp_path)
    source = tmp_path / "worker.mjs"
    source.write_text("export default {};")
    ops.private_write(
        tmp_path / "authority.wrangler.json", {"name": "fixture", "main": str(source)}
    )
    private_value = "fixture-sensitive-operator-value"
    monkeypatch.setattr(
        ops,
        "wrangler",
        lambda *args: (
            SimpleNamespace(returncode=1, stdout="", stderr="[code: 10007]")
            if args[0] == "deployments"
            else SimpleNamespace(
                returncode=0,
                stdout="https://fixture.example.workers.dev\n" + private_value,
                stderr="",
            )
        ),
    )
    ops.deploy("authority")
    assert private_value not in (tmp_path / "authority.deploy-log.json").read_text()
    assert ops.read_private(tmp_path / "authority.endpoint.json")["url"].endswith("/command")


def test_missing_external_runtime_configuration_keeps_factory_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("rj_studio_ai.waha_cloudflare.Path", lambda _: tmp_path / "missing.json")
    with pytest.raises(AuthorityClosed, match="private_runtime_authority_configuration_required"):
        create_waha_cloudflare_app()


def test_private_operator_material_cannot_be_overwritten_or_world_readable(tmp_path):
    target = tmp_path / "operator.json"
    ops.private_write(target, {"fixture": True})
    with pytest.raises(FileExistsError):
        ops.private_write(target, {"replaced": True})
    target.chmod(0o644)
    with pytest.raises(ValueError, match="not_0600"):
        ops.read_private(target)
