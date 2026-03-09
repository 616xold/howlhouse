from __future__ import annotations

import argparse
from pathlib import Path

from howlhouse.core.config import Settings
from howlhouse.platform.blob_store import create_blob_store
from howlhouse.platform.store import MatchStore
from howlhouse.recap import generate_share_cards


def _resolve_match_ids(
    store: MatchStore, *, requested_match_ids: list[str] | None, regenerate_all: bool
) -> list[str]:
    if requested_match_ids:
        return requested_match_ids
    if not regenerate_all:
        raise ValueError("provide at least one --match-id or pass --all")
    match_ids: list[str] = []
    for record in store.list_matches(include_hidden=True):
        if store.get_recap(record.match_id) is not None:
            match_ids.append(record.match_id)
    return match_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate persisted share-card artifacts from stored recap JSON. "
            "Use this after changing backend/howlhouse/recap/share_card.py "
            "when existing matches should keep serving the new design."
        )
    )
    parser.add_argument(
        "--match-id",
        action="append",
        dest="match_ids",
        default=None,
        help="Specific match_id to regenerate. Pass multiple times for more than one match.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Regenerate every match that already has a stored recap.",
    )
    args = parser.parse_args()

    settings = Settings()
    store = MatchStore(settings.database_url)
    blob_store = create_blob_store(settings)
    store.init_schema()

    try:
        match_ids = _resolve_match_ids(
            store,
            requested_match_ids=args.match_ids,
            regenerate_all=args.all,
        )
        if not match_ids:
            print("No stored recap-backed matches found.")
            return

        for match_id in match_ids:
            recap_record = store.get_recap(match_id)
            if recap_record is None:
                raise ValueError(f"Match does not have a stored recap: {match_id}")

            output_dir = Path(recap_record.share_card_public_path).parent
            public_path, spoilers_path = generate_share_cards(
                match_id,
                recap_record.recap,
                output_dir,
            )

            public_bytes = Path(public_path).read_bytes()
            spoilers_bytes = Path(spoilers_path).read_bytes()

            if recap_record.share_card_public_key:
                blob_store.put_bytes(
                    recap_record.share_card_public_key,
                    public_bytes,
                    content_type="image/png",
                )
            if recap_record.share_card_spoilers_key:
                blob_store.put_bytes(
                    recap_record.share_card_spoilers_key,
                    spoilers_bytes,
                    content_type="image/png",
                )

            print(
                f"regenerated {match_id} public={Path(public_path)} spoilers={Path(spoilers_path)}"
            )
    finally:
        store.close()


if __name__ == "__main__":
    main()
