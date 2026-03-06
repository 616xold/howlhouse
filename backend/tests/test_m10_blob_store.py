from __future__ import annotations

import pytest

from howlhouse.platform.blob_store import LocalBlobStore, S3BlobStore

try:
    import boto3
    from moto import mock_aws
except Exception:  # pragma: no cover - optional dependency path
    boto3 = None
    mock_aws = None


def test_local_blob_store_roundtrip(tmp_path):
    store = LocalBlobStore(tmp_path)

    key = "matches/match_1/replay.jsonl"
    payload = b'{"v":1}\n'
    store.put_bytes(key, payload, content_type="application/x-ndjson")

    assert store.exists(key)
    assert store.get_bytes(key) == payload
    assert store.uri_for_key(key) == "local://matches/match_1/replay.jsonl"


if boto3 is None or mock_aws is None:

    @pytest.mark.skip(reason="boto3 and moto are required for S3 blob-store tests")
    def test_s3_blob_store_roundtrip():
        pass

else:

    @mock_aws
    def test_s3_blob_store_roundtrip():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        client.create_bucket(Bucket="howlhouse-test")

        store = S3BlobStore(
            bucket="howlhouse-test",
            endpoint_url=None,
            region="us-east-1",
            access_key="test",
            secret_key="test",
            prefix="env/dev",
        )

        key = "matches/match_2/recap.json"
        store.put_text(key, '{"ok":true}')

        assert store.exists(key)
        assert store.get_text(key) == '{"ok":true}'
        assert store.uri_for_key(key) == "s3://howlhouse-test/env/dev/matches/match_2/recap.json"
