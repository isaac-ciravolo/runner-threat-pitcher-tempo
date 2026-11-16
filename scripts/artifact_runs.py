"""Publish paired result/model directories through one atomic completion pointer.

Files are written to private staging directories and then moved to immutable,
unique run directories. Only replacing current_run.json publishes a run. Failed
runs never change that pointer; their staging/orphan directories are retained
for diagnosis. Readers resolve and validate the pointer once per operation.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import uuid

from scripts.pipeline_validation import require, sha256_file


@dataclass(frozen=True)
class RunPaths:
    results: Path
    local: Path


def _inventory(directory):
    return {
        str(path.relative_to(directory).as_posix()): sha256_file(path)
        for path in sorted(directory.rglob('*')) if path.is_file()
    }


def _replace_pointer(path, payload):
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(payload, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class StagedRun:
    def __init__(self, output_dir, local_dir):
        self.output_dir = Path(output_dir).resolve()
        self.local_dir = Path(local_dir).resolve()
        require(
            self.output_dir != self.local_dir
            and self.output_dir not in self.local_dir.parents
            and self.local_dir not in self.output_dir.parents,
            'Results and local artifact roots must be separate directories',
        )
        self.run_id = uuid.uuid4().hex
        self.paths = RunPaths(
            self.output_dir / '.staging' / self.run_id,
            self.local_dir / '.staging' / self.run_id,
        )
        self.paths.results.mkdir(parents=True)
        self.paths.local.mkdir(parents=True)

    def publish(self, validate):
        """Validate staged contents; leave the previous run intact on failure."""
        validate(self.paths)
        inventory = {
            'results': _inventory(self.paths.results),
            'local': _inventory(self.paths.local),
        }
        require(all(inventory.values()), 'Cannot publish empty artifact directories')
        completed = RunPaths(
            self.output_dir / 'runs' / self.run_id,
            self.local_dir / 'runs' / self.run_id,
        )
        completed.results.parent.mkdir(parents=True, exist_ok=True)
        completed.local.parent.mkdir(parents=True, exist_ok=True)
        manifest = {'schema_version': 1, 'run_id': self.run_id, 'files': inventory}
        (self.paths.results / 'manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n', encoding='utf-8'
        )
        # Each destination is unique; no existing completed files are replaced.
        os.replace(self.paths.local, completed.local)
        os.replace(self.paths.results, completed.results)
        pointer = {
            'schema_version': 1,
            'run_id': self.run_id,
            'manifest_sha256': sha256_file(completed.results / 'manifest.json'),
        }
        _replace_pointer(self.output_dir / 'current_run.json', pointer)
        return completed


def resolve_run(output_dir, local_dir):
    """Return one verified completed run, or the pre-publication legacy snapshot.

Legacy snapshots remain readable without rewriting committed research results.
A malformed pointer never falls back to legacy files.
"""
    output_dir, local_dir = Path(output_dir).resolve(), Path(local_dir).resolve()
    pointer_path = output_dir / 'current_run.json'
    if not pointer_path.exists():
        require(
            (output_dir / 'provenance.json').is_file()
            and (local_dir / 'final_bundle.joblib').is_file(),
            f'No completed forward run at {output_dir}',
        )
        return RunPaths(output_dir, local_dir)
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    run_id = pointer['run_id']
    require(
        isinstance(run_id, str) and len(run_id) == 32
        and all(c in '0123456789abcdef' for c in run_id),
        'Invalid published run ID',
    )
    require(pointer.get('schema_version') == 1, 'Unsupported run pointer schema')
    paths = RunPaths(output_dir / 'runs' / run_id, local_dir / 'runs' / run_id)
    manifest_path = paths.results / 'manifest.json'
    require(sha256_file(manifest_path) == pointer['manifest_sha256'], 'Run manifest checksum mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest.get('run_id') == run_id and manifest.get('schema_version') == 1, 'Run manifest identity mismatch')
    for kind, directory in [('results', paths.results), ('local', paths.local)]:
        observed = _inventory(directory)
        if kind == 'results':
            observed.pop('manifest.json', None)
        require(observed == manifest['files'][kind], f'Published {kind} artifacts do not match manifest')
    return paths
