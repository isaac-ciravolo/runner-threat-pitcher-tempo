"""Run the frozen forward model on separately rebuilt chronology-v2 data."""
import json
from scripts.recorded_attempt_baseline import ROOT
from scripts.forward_threat import main

if __name__=='__main__':
    provenance=json.loads((ROOT/'results/chronology_repair/repaired_provenance.json').read_text())
    main(input_dir=ROOT/'data/processed/chronology_repair',output_dir=ROOT/'results/forward_threat_v2',local_dir=ROOT/'data/processed/forward_threat_v2',verified_hashes=provenance['repaired_input_hashes'],use_availability=True)

    import hashlib
    path=ROOT/'results/forward_threat_v2/provenance.json'
    record=json.loads(path.read_text())
    record['chronology_version']='event_bounds_v2'
    record['history_availability_field']='history_available_after_utc'
    record['repair_hashes']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['docs/chronology_repair_protocol.md','docs/chronology_timing_dispositions.md','results/chronology_repair/repaired_provenance.json']}
    path.write_text(json.dumps(record,indent=2)+'\n')
