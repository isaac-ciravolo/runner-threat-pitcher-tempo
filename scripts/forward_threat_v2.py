"""Run the frozen forward model on separately rebuilt chronology-v2 data."""
import json
from scripts.recorded_attempt_baseline import ROOT
from scripts.forward_threat import main as run_forward
from scripts.pipeline_validation import sha256_file


def main():
    provenance=json.loads((ROOT/'results/chronology_repair/repaired_provenance.json').read_text(encoding='utf-8'))
    extra = {
        'chronology_version': 'event_bounds_v2',
        'history_availability_field': 'history_available_after_utc',
        'repair_hashes': {name:sha256_file(ROOT/name) for name in [
            'docs/chronology_repair_protocol.md',
            'docs/chronology_timing_dispositions.md',
            'results/chronology_repair/repaired_provenance.json',
        ]},
    }
    return run_forward(
        input_dir=ROOT/'data/processed/chronology_repair',
        output_dir=ROOT/'results/forward_threat_v2',
        local_dir=ROOT/'data/processed/forward_threat_v2',
        verified_hashes=provenance['repaired_input_hashes'],
        use_availability=True,
        provenance_extra=extra,
    )


if __name__=='__main__':
    main()
