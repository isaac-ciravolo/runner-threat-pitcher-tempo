"""Export descriptive calibration plots with bin denominators and run lineage."""
import argparse
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from scripts.artifact_runs import resolve_run
from scripts.pipeline_validation import sha256_file
from scripts.recorded_attempt_baseline import ROOT


def main(stage):
    settings = {
        'baseline': ('recorded_attempt_grouped', 'heldout_2024', ['context', 'separate_history'],
                     ['Context', 'Context + runner histories'], 'Recorded steal attempts'),
        'forward': ('forward_threat_grouped', 'development_2024', ['raw', 'prospective_calibrated'],
                    ['Raw forward threat', 'Training-fitted recalibration candidate'], 'Recorded steal attempts'),
        'response': ('pitcher_response_grouped', 'development_2024', ['context', 'context_threat'],
                     ['Context', 'Context + forward threat'], 'Recorded pitcher pickoffs'),
    }
    root, split, models, labels, outcome = settings[stage]
    run = resolve_run(ROOT / 'results' / root, ROOT / 'data/processed' / root)
    path = run.results / 'calibration.csv'
    table = pd.read_csv(path)
    table = table[table.split.eq(split) & table.n.gt(0)]
    if stage == 'response':
        table = table[table.variant.eq('primary')]
    fig = plt.figure(figsize=(11, 8.5), layout='constrained')
    grid = fig.add_gridspec(2, 2, height_ratios=[3, 2])
    colors = ['#24618a', '#ae4f1e']
    groups = [table[table.model.eq(model)].sort_values('mean_prediction') for model in models]
    if any(group.empty for group in groups):
        raise ValueError('Missing calibration series')
    maximum = max(.05, *(group[['mean_prediction', 'observed_rate']].max().max() for group in groups))
    limit = min(1, maximum * 1.08)
    for index, (group, label, color) in enumerate(zip(groups, labels, colors)):
        ax = fig.add_subplot(grid[0, index])
        ax.plot(group.mean_prediction, group.observed_rate, 'o-', color=color, linewidth=1.5)
        ax.plot([0, limit], [0, limit], '--', color='#777777', linewidth=1)
        ax.set(xlim=(0, limit), ylim=(0, limit), xlabel='Mean predicted probability',
               ylabel='Observed event proportion', title=label)
        ax.grid(alpha=.2)
        denominator = fig.add_subplot(grid[1, index])
        denominator.axis('off')
        cells = [[f'{row.n:,}', f'{row.mean_prediction:.4f}', f'{row.observed_rate:.4f}']
                 for row in group.itertuples()]
        tab = denominator.table(cellText=cells, colLabels=['Windows in bin', 'Predicted', 'Observed'],
                                loc='center', cellLoc='center')
        tab.auto_set_font_size(False)
        tab.set_fontsize(9)
        tab.scale(1, 1.45)
    fig.suptitle(f'{outcome}: 2024 development calibration', fontsize=15)
    fig.supxlabel('G3 completed-play windows | Recorded feed events | Fixed descriptive bins; no causal interpretation',
                  fontsize=9)
    directory = ROOT / 'results/grouped_calibration_figures'
    directory.mkdir(exist_ok=True)
    stem = f'{stage}_{run.results.name}'
    for extension in ('png', 'svg'):
        fig.savefig(directory / f'{stem}.{extension}', dpi=180)
    plt.close(fig)
    provenance = dict(stage=stage, run_id=run.results.name,
                      manifest_sha256=sha256_file(run.results / 'manifest.json'),
                      calibration_sha256=sha256_file(path), script_sha256=sha256_file(__file__))
    (directory / f'{stem}.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(directory / f'{stem}.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['baseline', 'forward', 'response'])
    main(parser.parse_args().stage)
