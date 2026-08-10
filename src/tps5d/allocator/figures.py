"""Figures for the allocator.

Style follows what Physics in Medicine and Biology and Medical Physics expect.

Every figure takes a `synthetic` flag. When true a corner marker is drawn.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from tps5d.allocator.dominance import pareto, hull

COLORS = {
    'P0': '#000000',
    'P1': '#E69F00',
    'P2a': '#56B4E9',
    'P2b': '#009E73',
    'P3': '#0072B2',
}
GREY = '#7F7F7F'
MM = 1.0 / 25.4
COL1, COL2 = 90 * MM, 180 * MM      # single and double column width

def use_style():
    """Apply the manuscript style. Call once before making figures."""
    mpl.rcParams.update({
        'figure.dpi': 120,
        'savefig.dpi': 600,
        'savefig.bbox': 'tight',
        'font.family': 'sans-serif',
        'font.size': 8,
        'axes.labelsize': 8,
        'axes.titlesize': 8,
        'axes.linewidth': 0.6,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'xtick.major.width': 0.6,
        'ytick.major.width': 0.6,
        'legend.fontsize': 7,
        'legend.frameon': False,
        'lines.linewidth': 1.2,
        'lines.markersize': 3.5,
        'grid.linewidth': 0.4,
        'grid.color': '#DDDDDD',
    })

def _mark_synthetic(ax, on, where = 'above'):
    """Corner marker. `where` avoids collisions with a legend placed above."""
    if not on:
        return
    pos = {'above': (0.995, 1.02, 'right', 'bottom'),
           'inside': (0.995, 0.02, 'right', 'bottom')}[where]
    ax.text(pos[0], pos[1], 'SYNTHETIC COHORT', transform = ax.transAxes,
            ha = pos[2], va = pos[3], fontsize = 6, color = '#B03A2E', fontweight = 'bold')

def _save(fig, path):
    if path:
        fig.savefig(path)
        fig.savefig(str(path).rsplit('.', 1)[0] + '.png')
    return fig

def policy_curves(records, path = None, synthetic = True):
    """Cohort delta NTCP against adaptation time, one line per policy.

    The reference study's central figure, generalised: there the lines were
    margin arms under one allocation rule, here they are allocation rules. P0
    is drawn as a dashed reference, since it is current practice and the
    question is which policies sit above it.
    """
    fig, ax = plt.subplots(figsize = (COL1, 62 * MM))
    pols = sorted({r['policy'] for r in records}, key = lambda p: list(COLORS).index(p))

    for p in pols:
        rs = sorted([r for r in records if r['policy'] == p], key = lambda r: r['dtau'])
        x = [r['dtau'] for r in rs]
        y = [100 * r['mean_dntcp'] for r in rs]
        if p == 'P0':
            ax.plot(x, y, ls = '--', color = COLORS[p], label = 'P0, current practice')
        else:
            ax.plot(x, y, marker = 'o', color = COLORS[p], label = p)

    ax.set_xlabel(r'extra time per adapted fraction, $\Delta\tau$  (min)')
    ax.set_ylabel(r'cohort mean $\Delta$NTCP  (%)')
    ax.grid(axis='y')
    ax.legend(loc = 'best', ncols = 2)
    _mark_synthetic(ax, synthetic)
    fig.tight_layout()
    return _save(fig, path)

def shadow_price(records, path = None, synthetic = True):
    """The shadow price against adaptation time.

    Lambda is the cohort delta NTCP bought by one additional machine-minute. A
    workflow change costing an extra delta tau per fraction is worthwhile for a
    patient exactly when the utility it buys exceeds lambda times that time, so
    this curve is the exchange rate behind the reference study's threshold.
    """
    rs = sorted({r['dtau']: r for r in records}.values(), key=lambda r: r['dtau'])
    fig, ax = plt.subplots(figsize = (COL1, 58 * MM))
    ax.plot([r['dtau'] for r in rs], [1e4 * r['lambda'] for r in rs],
            marker='o', color=COLORS['P3'])
    ax.set_xlabel(r'extra time per adapted fraction, $\Delta\tau$  (min)')
    ax.set_ylabel(r'$\lambda$  ($\Delta$NTCP % per 100 machine-min)')
    ax.grid(axis='y')
    _mark_synthetic(ax, synthetic)
    fig.tight_layout()
    return _save(fig, path)

def cohort_composition(records, policy = 'P3', path = None, synthetic = True):
    """Who receives what, as a function of adaptation time.

    The quantitative form of the reference study's patient icons: as adaptation
    lengthens, patients are displaced from protons to photons. With per-block
    adaptation the intermediate categories can also be occupied, and whether
    they are is the question the allocator exists to answer.
    """
    rs = sorted([r for r in records if r['policy'] == policy],
                key=lambda r: r['dtau'])
    labels = sorted({k[2:] for r in rs for k in r if k.startswith('n_PT')} |
                    {k[2:] for r in rs for k in r if k.startswith('n_photons')})
    labels = [l for l in labels if l]
    order = [l for l in labels if l == 'photons'] + \
            sorted([l for l in labels if l != 'photons'])

    fig, ax = plt.subplots(figsize = (COL1, 58 * MM))
    x = np.arange(len(rs))
    bottom = np.zeros(len(rs))
    shades = plt.cm.Blues(np.linspace(0.35, 0.85, max(len(order) - 1, 1)))
    for i, lab in enumerate(order):
        vals = np.array([r.get(f'n_{lab}', 0) for r in rs], dtype=float)
        col = GREY if lab == 'photons' else shades[i - 1]
        ax.bar(x, vals, bottom = bottom, color = col, width = 0.72,
               edgecolor = 'white', linewidth = 0.4, label = lab)
        bottom += vals

    ax.set_xticks(x, [f"{r['dtau']:g}" for r in rs])
    ax.set_xlabel(r'$\Delta\tau$  (min)')
    ax.set_ylabel('patients')
    ax.legend(loc = 'upper center', bbox_to_anchor=(0.5, 1.22), ncols = 3)
    _mark_synthetic(ax, synthetic, where = 'inside')
    fig.tight_layout()
    return _save(fig, path)

def option_ladder(cohort, pid, path = None, synthetic = True):
    """One patient's option set, with the two reductions drawn.

    A methods figure rather than a result. It shows why ranking whole
    strategies by benefit density is the wrong statistic: every patient already
    holds the photon option at zero proton cost, so the decision is which rung
    to climb to, and the slopes between consecutive surviving options are what
    the allocation compares across patients.
    """
    opts = cohort.by_patient()[pid]
    pts = [(s.occupancy, 100 * cohort.dntcp(s)) for s in opts]
    i_par, i_hull = pareto(pts), hull(pts)

    fig, ax = plt.subplots(figsize = (COL1, 62 * MM))

    dominated = [i for i in range(len(pts)) if i not in i_par]
    lp_only = [i for i in i_par if i not in i_hull]

    if dominated:
        ax.scatter([pts[i][0] for i in dominated], [pts[i][1] for i in dominated],
                   marker = 'x', color = GREY, label = 'Pareto dominated', zorder = 3)
    if lp_only:
        ax.scatter([pts[i][0] for i in lp_only], [pts[i][1] for i in lp_only],
                   facecolors = 'none', edgecolors = COLORS['P1'],
                   label = 'LP dominated', zorder = 3)

    hx = [pts[i][0] for i in i_hull]
    hy = [pts[i][1] for i in i_hull]
    ax.plot(hx, hy, color = COLORS['P3'], marker = 'o', zorder = 4,
            label = 'upper hull, selectable')

    for i, (x, y) in enumerate(pts):
        on_hull = i in i_hull
        ax.annotate(opts[i].sid, (x, y), textcoords = 'offset points',
                    xytext = (5, -7), fontsize = 6,
                    color=COLORS['P3'] if on_hull else GREY)

    # Incremental efficiency is the slope of each hull segment, and it is what
    # the allocation ranks across patients.
    for a, b in zip(i_hull, i_hull[1:]):
        dx = pts[b][0] - pts[a][0]
        dy = pts[b][1] - pts[a][1]
        ax.annotate(f"{dy / dx:.3f}",
                    (0.5 * (pts[a][0] + pts[b][0]), 0.5 * (pts[a][1] + pts[b][1])),
                    textcoords = 'offset points', xytext = (0, 6), fontsize = 6,
                    ha = 'center', color = GREY)

    ax.set_xlabel('course occupancy  (machine-min)')
    ax.set_ylabel(r'$\Delta$NTCP against baseline  (%)')
    ax.grid(axis = 'y')
    ax.legend(loc = 'lower right')
    _mark_synthetic(ax, synthetic)
    fig.tight_layout()
    return _save(fig, path)